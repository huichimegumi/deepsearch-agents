"""
主智能体组装与异步执行模块

负责把模型、主提示词、文件类工具和三个专家子智能体组装成 DeepAgent，
并提供 run_deep_agent 作为后续 API 层调用的统一入口。运行时还会为每个
session_id 创建独立工作目录，并把工具调用、子智能体调用和最终结果推送给前端。
"""

import asyncio
import shutil
import uuid
from functools import lru_cache
from pathlib import Path

from deepagents import create_deep_agent

from app.agent.llm import get_model
from app.agent.prompts import main_agent_content
from app.agent.research_workflow import (
    RESEARCH_PHASES,
    ResearchPhase,
    build_degraded_phase_output,
    build_phase_prompt,
)
from app.agent.runtime import (
    ResearchBudget,
    ResearchRunTrace,
    reset_research_runtime,
    set_research_runtime,
)
from app.agent.subagents.database_query_agent import database_query_agent
from app.agent.subagents.knowledge_base_agent import knowledge_base_agent
from app.agent.subagents.network_search_agent import network_search_agent
from app.api.audit import write_audit_event
from app.api.context import (
    reset_research_phase_context,
    reset_session_context,
    set_research_phase_context,
    set_session_context,
    set_thread_context,
    set_user_context,
)
from app.api.monitor import monitor
from app.config import AgentExecutionBudget, get_settings
from app.memory.checkpoint import get_short_term_checkpointer
from app.memory.service import format_memories_for_prompt, search_memories

# 文件类工具由主智能体直接掌握，负责读取上传附件和生成最终交付文档
from app.tools.markdown_tools import generate_markdown
from app.tools.memory_tools import remember_user_memory, search_user_memory
from app.tools.pdf_tools import convert_md_to_pdf
from app.tools.upload_file_read_tool import read_file_content


@lru_cache(maxsize=1)
def get_planner_agent():
    """Build a tool-free agent for planning and evidence compression phases."""
    return create_deep_agent(
        model=get_model(),
        system_prompt=main_agent_content["system_prompt"],
        tools=[],
        checkpointer=get_short_term_checkpointer(),
        subagents=[],
    )


@lru_cache(maxsize=1)
def get_research_agent():
    """Build the only phase agent that can call researcher subagents."""
    return create_deep_agent(
        model=get_model(),
        system_prompt=main_agent_content["system_prompt"],
        tools=[
            read_file_content,
            remember_user_memory,
            search_user_memory,
        ],
        checkpointer=get_short_term_checkpointer(),
        subagents=[database_query_agent, network_search_agent, knowledge_base_agent],
    )


@lru_cache(maxsize=1)
def get_writer_agent():
    """Build a write-only agent for synthesis phases that must not call researchers."""
    return create_deep_agent(
        model=get_model(),
        system_prompt=main_agent_content["system_prompt"],
        tools=[
            generate_markdown,
            convert_md_to_pdf,
        ],
        checkpointer=get_short_term_checkpointer(),
        subagents=[],
    )


def get_main_agent():
    """Backward-compatible accessor for the research-capable agent."""
    return get_research_agent()


# 当前文件位于 app/agent/main_agent.py，parents[1] 即 app 目录
project_root_path = Path(__file__).parents[1].resolve()


class PhaseBudgetExceeded(RuntimeError):
    """Raised when an in-process phase guard decides the phase must stop."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def _astream_with_runtime_limit(agent, payload, config, timeout_seconds: float):
    if timeout_seconds <= 0:
        async for chunk in agent.astream(payload, config=config):
            yield chunk
        return

    async with asyncio.timeout(timeout_seconds):
        async for chunk in agent.astream(payload, config=config):
            yield chunk


def _classify_budget_profile(task_query: str) -> str:
    """Classify the task into a coarse execution budget profile."""
    normalized = task_query.lower()
    deep_markers = (
        "报告",
        "研报",
        "pdf",
        "markdown",
        "竞品",
        "趋势",
        "行业分析",
        "深度研究",
        "完整",
        "引用",
        "来源",
        "多源",
        "whitepaper",
        "report",
        "competitive",
        "analysis",
    )
    quick_markers = (
        "简单",
        "简短",
        "一句话",
        "快速",
        "quick",
        "brief",
    )
    if any(marker in normalized for marker in deep_markers):
        return "deep_report"
    if len(task_query) < 80 and any(marker in normalized for marker in quick_markers):
        return "quick"
    return "standard"


def _phase_thread_id(thread_id: str, phase_key: str, workflow_run_id: str) -> str:
    """Return an isolated checkpoint id for one workflow phase."""
    return f"{thread_id}__run__{workflow_run_id}__phase__{phase_key}"


def _phase_config(
    thread_id: str,
    phase_key: str,
    budget: AgentExecutionBudget,
    workflow_run_id: str = "current",
) -> dict:
    """Build the LangGraph config for one phase using its own budget."""
    return {
        "configurable": {"thread_id": _phase_thread_id(thread_id, phase_key, workflow_run_id)},
        "recursion_limit": budget.recursion_limit,
    }


def _budget_payload(
    *,
    budget: AgentExecutionBudget,
    budget_profile: str,
    remaining_workflow_seconds: float | None = None,
) -> dict:
    payload = {
        "budget_profile": budget_profile,
        "recursion_limit": budget.recursion_limit,
        "timeout_seconds": budget.timeout_seconds,
    }
    if remaining_workflow_seconds is not None:
        payload["remaining_workflow_seconds"] = max(0.0, remaining_workflow_seconds)
    return payload


def _phase_agent_for(
    *,
    phase: ResearchPhase,
    planner_agent,
    research_agent,
    writer_agent,
):
    """Select the backend-enforced capability set for a workflow phase."""
    if phase.key == "final_report":
        return writer_agent
    if phase.requires_tools:
        return research_agent
    return planner_agent


def _max_subagent_calls_for_profile(budget_profile: str) -> int:
    """Keep supervisor research from expanding into an unbounded task fan-out."""
    if budget_profile == "quick":
        return 2
    if budget_profile == "deep_report":
        return 8
    return 4


async def _run_agent_phase(
    *,
    agent,
    phase: ResearchPhase,
    prompt: str,
    config: dict,
    budget: AgentExecutionBudget,
    budget_profile: str,
    research_budget: ResearchBudget,
    run_trace: ResearchRunTrace,
    remaining_workflow_seconds: float | None = None,
    max_subagent_calls: int | None = None,
    emit_final_result: bool = False,
) -> str | None:
    """Run one enforced research phase and return the latest model text."""
    budget_data = _budget_payload(
        budget=budget,
        budget_profile=budget_profile,
        remaining_workflow_seconds=remaining_workflow_seconds,
    )
    run_trace.start_phase(phase.key, phase.title)
    if phase.requires_tools and not research_budget.take_research_round():
        run_trace.finish_phase(phase.key, "budget_exceeded", "research_round_limit")
        return None
    monitor.report_research_phase(phase.key, phase.title, "start", budget_data)
    write_audit_event(
        "research_phase_started",
        {"phase_key": phase.key, "phase_title": phase.title, **budget_data},
    )

    phase_result = None
    phase_status = "end"
    phase_error = None
    budget_reason = None
    subagent_call_count = 0
    phase_token = set_research_phase_context(phase.key)
    try:
        async for chunk in _astream_with_runtime_limit(
            agent,
            {"messages": [{"role": "user", "content": prompt}]},
            config,
            budget.timeout_seconds,
        ):
            # chunk 形如 {"model": {"messages": [...]}}，这里主要关心模型最新消息
            for node_name, state in chunk.items():
                if not state or "messages" not in state:
                    continue
                messages = state["messages"]
                if not (messages and isinstance(messages, list)):
                    continue
                last_msg = messages[-1]
                if node_name != "model":
                    continue

                run_trace.record_llm_call(phase.key, last_msg)
                if not research_budget.take_llm_call(phase.key):
                    raise PhaseBudgetExceeded("llm_call_limit")

                tool_calls = getattr(last_msg, "tool_calls", None)
                if tool_calls:
                    # DeepAgents 调用子智能体时，本质上会产生名为 task 的工具调用
                    for tool_call in tool_calls:
                        run_trace.record_tool_call(phase.key, tool_call["name"])
                        if tool_call["name"] == "task":
                            subagent_call_count += 1
                            if (
                                max_subagent_calls is not None
                                and subagent_call_count > max_subagent_calls
                            ):
                                raise PhaseBudgetExceeded("subagent_call_limit")
                            # 子智能体调用单独上报，前端可以展示“正在调用哪个专家助手”
                            monitor.report_assistant(
                                tool_call["args"]["subagent_type"],
                                {"description": tool_call["args"]["description"]},
                            )
                elif last_msg.content:
                    phase_result = last_msg.content
                    if emit_final_result:
                        # 只有最终报告阶段才反馈给前端和会话历史，避免把 brief 当成最终答案
                        print(f"主智能体执行结果，最终结果：{last_msg.content[:100]}")
                        monitor.report_task_result(last_msg.content)
                        write_audit_event(
                            "task_result",
                            {"result": last_msg.content},
                        )
    except asyncio.CancelledError:
        phase_status = "cancelled"
        budget_reason = "cancelled"
        raise
    except TimeoutError as exc:
        phase_status = "budget_exceeded"
        phase_error = repr(exc)
        budget_reason = "timeout"
        message = (
            f"Research phase {phase.key} exceeded its execution budget; "
            "continuing with available evidence"
        )
        monitor._emit("phase_budget_exceeded", message, {"phase_key": phase.key, **budget_data})
        write_audit_event(
            "research_phase_budget_exceeded",
            {
                "phase_key": phase.key,
                "phase_title": phase.title,
                "reason": budget_reason,
                "error": phase_error,
                **budget_data,
            },
        )
    except PhaseBudgetExceeded as exc:
        phase_status = "budget_exceeded"
        phase_error = repr(exc)
        budget_reason = exc.reason
        message = (
            f"Research phase {phase.key} reached its {exc.reason}; "
            "continuing with available evidence"
        )
        monitor._emit("phase_budget_exceeded", message, {"phase_key": phase.key, **budget_data})
        write_audit_event(
            "research_phase_budget_exceeded",
            {
                "phase_key": phase.key,
                "phase_title": phase.title,
                "reason": budget_reason,
                "error": phase_error,
                **budget_data,
            },
        )
    except Exception as exc:
        if exc.__class__.__name__ != "GraphRecursionError":
            phase_status = "error"
            phase_error = repr(exc)
            budget_reason = exc.__class__.__name__
            raise
        phase_status = "budget_exceeded"
        phase_error = repr(exc)
        budget_reason = "recursion_limit"
        message = (
            f"Research phase {phase.key} reached its recursion budget; "
            "continuing with available evidence"
        )
        monitor._emit("phase_budget_exceeded", message, {"phase_key": phase.key, **budget_data})
        write_audit_event(
            "research_phase_budget_exceeded",
            {
                "phase_key": phase.key,
                "phase_title": phase.title,
                "reason": budget_reason,
                "error": phase_error,
                **budget_data,
            },
        )
    finally:
        reset_research_phase_context(phase_token)
        run_trace.finish_phase(phase.key, phase_status, budget_reason)

    phase_end_data = {
        "result_preview": (phase_result or "")[:500],
        "subagent_call_count": subagent_call_count,
        **budget_data,
    }
    if phase_error:
        phase_end_data["error"] = phase_error
    if budget_reason:
        phase_end_data["reason"] = budget_reason
    monitor.report_research_phase(
        phase.key,
        phase.title,
        phase_status,
        phase_end_data,
    )
    write_audit_event(
        "research_phase_finished",
        {
            "phase_key": phase.key,
            "phase_title": phase.title,
            "status": phase_status,
            "result_preview": (phase_result or "")[:500],
            "subagent_call_count": subagent_call_count,
            **budget_data,
        },
    )
    return phase_result


def _requires_knowledge_base_first(task_query: str) -> bool:
    """Return True when the user is asking about content inside a local document."""
    document_markers = (
        "白皮书",
        "研报",
        "报告",
        "pdf",
        "PDF",
        "文档",
        "文件",
        "资料",
        "手册",
    )
    content_markers = (
        "里提到",
        "中提到",
        "提到的",
        "里面",
        "其中",
        "原文",
        "摘取",
        "提取",
        "市场份额",
        "营收",
        "收入",
        "市场规模",
    )
    return any(marker in task_query for marker in document_markers) and any(
        marker in task_query for marker in content_markers
    )


def _requires_local_knowledge_base_only(task_query: str) -> bool:
    """Return True when the user explicitly restricts the task to local knowledge."""
    local_markers = ("本地知识库", "知识库助手", "RAG", "rag")
    exclusivity_markers = (
        "只使用",
        "仅使用",
        "只能使用",
        "不要使用网络",
        "不要网络搜索",
        "不要联网",
        "不使用网络",
        "不联网",
        "禁止网络搜索",
    )
    return any(marker in task_query for marker in local_markers) and any(
        marker in task_query for marker in exclusivity_markers
    )


async def run_deep_agent(
    task_query,
    session_id,
    user_id: str | None = None,
    monitor_thread_id: str | None = None,
    conversation_memory: str = "",
    budget_profile_override: str | None = None,
):
    """
    异步流式执行主智能体

    API 层会为每次任务传入用户问题和 session_id。本函数负责准备会话目录、
    复制上传文件、写入 ContextVar，并在流式执行过程中把关键事件上报给前端。
    :param task_query: 前端提交的原始任务问题
    :param session_id: 当前任务 ID，同时用于 thread_id、输出目录和 WebSocket 定向推送
    """
    event_thread_id = monitor_thread_id or session_id
    settings = get_settings()
    allowed_profiles = {"quick", "standard", "deep_report", "thorough"}
    budget_profile = (
        budget_profile_override
        if budget_profile_override in allowed_profiles
        else _classify_budget_profile(task_query)
    )
    workflow_run_id = uuid.uuid4().hex
    research_budget = ResearchBudget(settings.research_budget_limits(budget_profile))
    run_trace = ResearchRunTrace(
        run_id=workflow_run_id,
        thread_id=event_thread_id,
        budget_profile=budget_profile,
        budget=research_budget,
    )
    print(f"[MainAgent] 开始执行会话，session_id={session_id}")
    write_audit_event(
        "task_started",
        {
            "query": task_query,
        },
        thread_id=event_thread_id,
    )

    # 每个会话独立使用 output/session_{session_id}，避免不同用户的产物互相覆盖
    session_parent = project_root_path / "output"
    if user_id:
        session_parent = session_parent / f"user_{user_id}"
    session_dir = session_parent / f"session_{session_id}"
    session_dir.mkdir(parents=True, exist_ok=True)

    # 前端和工具使用绝对路径；提示词里只给模型相对路径，降低模型误用系统绝对路径的概率
    session_dir_str = str(session_dir).replace("\\", "/")
    relative_session_dir_str = str(session_dir.relative_to(project_root_path)).replace("\\", "/")

    # 上传文件先落在 updated/session_{session_id}，执行前复制到本次 output 工作目录
    # 这样读文件工具和生成文件工具都只需要围绕同一个 session_dir 工作
    updated_parent = project_root_path / "updated"
    if user_id:
        updated_parent = updated_parent / f"user_{user_id}"
    updated_dir_path = updated_parent / f"session_{session_id}"
    updated_info_prompt = ""
    if updated_dir_path.exists():
        files = [f.name for f in updated_dir_path.iterdir() if f.is_file()]
        if files:
            for filename in files:
                # copy2 会保留上传文件的修改时间、权限等元数据，便于后续排查文件来源
                shutil.copy2(updated_dir_path / filename, session_dir / filename)

            # 把上传文件列表注入用户消息，提醒模型先调用 read_file_content 获取附件内容
            updated_info_prompt = (
                "\n    [已上传文件] 已加载到工作目录:\n"
                + "\n".join([f"    - {f}" for f in files])
                + "\n    请优先使用工具（read_file_content）读取并参考这些文件。"
            )

    # ContextVar 让深层工具无需显式传参，也能拿到当前会话目录和 WebSocket thread_id
    session_dir_token = set_session_context(session_dir_str)
    session_id_token = set_thread_context(event_thread_id)
    user_id_token = set_user_context(user_id) if user_id else None

    monitor._emit(
        "research_run_started",
        f"研究任务使用 {budget_profile} 预算",
        {
            "run_id": workflow_run_id,
            "budget_profile": budget_profile,
            "budget": research_budget.snapshot(),
        },
    )

    # 前端拿到工作目录后，可以展示本次任务生成的 Markdown/PDF 等产物
    monitor.report_session_dir(session_dir_str)

    # checkpointer 依赖 thread_id 区分会话记忆；同一 session_id 会复用同一条执行上下文
    # 工作环境指令是运行时动态补充的，约束模型只在当前会话目录读写文件
    path_instruction = f"""
    【工作环境指令】
    工作目录: {relative_session_dir_str}
    {updated_info_prompt}

    规则：
    1. 新生成文件必须保存到工作目录：'{relative_session_dir_str}/filename'
    2. 读取已上传的文件时，请直接将文件名（例如：'开篇.txt'）作为 filename 参数传入（read_file_content）读取工具，不要带上任何目录前缀。
    3. 使用相对路径，禁止使用绝对路径
    4. 若存在上传文件，请先分析内容
    """

    source_routing_instruction = ""
    if _requires_knowledge_base_first(task_query):
        source_routing_instruction = """

    【信息源路由指令】
    用户正在询问具体白皮书、研报、报告、PDF 或文档中的内容。第一步必须调用“本地知识库助手”检索本地已索引文档；
    只有当本地知识库助手明确返回没有可用知识库、没有命中或证据不足时，才可以调用“网络搜索助手”补充公开信息。
    """
    if _requires_local_knowledge_base_only(task_query):
        source_routing_instruction += """

    【本地知识库限定】
    用户明确要求只使用本地知识库助手。本轮任务禁止调用“网络搜索助手”和任何互联网搜索工具；
    如果本地知识库助手没有找到答案或执行失败，必须直接说明本地知识库结果不足或失败原因，不得改用网络搜索补充。
    """

    memory_instruction = ""
    if user_id:
        try:
            memory_instruction = "\n\n" + format_memories_for_prompt(
                search_memories(user_id=user_id, query=task_query)
            )
        except Exception as exc:
            write_audit_event(
                "memory_retrieval_error",
                {"error": repr(exc)},
                thread_id=event_thread_id,
            )

    final_result = None
    run_status = "completed"
    run_failure_reason = None
    runtime_tokens = set_research_runtime(research_budget, run_trace)
    try:
        planner_agent = get_planner_agent()
        research_agent = get_research_agent()
        writer_agent = get_writer_agent()
        runtime_instructions = (
            path_instruction
            + source_routing_instruction
            + memory_instruction
            + ("\n\n" + conversation_memory if conversation_memory else "")
        )
        phase_outputs: dict[str, str] = {}
        max_subagent_calls = _max_subagent_calls_for_profile(budget_profile)

        for phase in RESEARCH_PHASES:
            remaining_workflow_seconds = research_budget.remaining_seconds
            phase_budget = settings.agent_phase_budget(phase.key, budget_profile)
            if remaining_workflow_seconds <= 0:
                reason = "run-level research budget was exhausted before this phase started"
                run_trace.start_phase(phase.key, phase.title)
                run_trace.finish_phase(phase.key, "budget_exceeded", "run_timeout")
                monitor._emit(
                    "workflow_budget_exceeded",
                    reason,
                    {
                        "phase_key": phase.key,
                        "phase_title": phase.title,
                        "budget_profile": budget_profile,
                        "hard_timeout_seconds": research_budget.limits.total_seconds,
                    },
                )
                write_audit_event(
                    "workflow_budget_exceeded",
                    {
                        "phase_key": phase.key,
                        "phase_title": phase.title,
                        "budget_profile": budget_profile,
                        "hard_timeout_seconds": research_budget.limits.total_seconds,
                    },
                    thread_id=event_thread_id,
                )
                phase_result = build_degraded_phase_output(
                    task_query=task_query,
                    phase=phase,
                    phase_outputs=phase_outputs,
                    reason=reason,
                )
                if phase.key == "final_report":
                    monitor.report_task_result(phase_result)
                    write_audit_event(
                        "task_result",
                        {
                            "result": phase_result,
                            "degraded": True,
                            "budget_profile": budget_profile,
                        },
                        thread_id=event_thread_id,
                    )
                phase_outputs[phase.key] = phase_result
                if phase.key == "final_report":
                    final_result = phase_result
                continue

            phase_budget = AgentExecutionBudget(
                recursion_limit=phase_budget.recursion_limit,
                timeout_seconds=research_budget.phase_timeout(
                    phase.key,
                    phase_budget.timeout_seconds,
                ),
            )
            config = _phase_config(
                event_thread_id,
                phase.key,
                phase_budget,
                workflow_run_id,
            )
            prompt = build_phase_prompt(
                task_query=task_query,
                phase=phase,
                phase_outputs=phase_outputs,
                runtime_instructions=runtime_instructions,
            )
            phase_agent = _phase_agent_for(
                phase=phase,
                planner_agent=planner_agent,
                research_agent=research_agent,
                writer_agent=writer_agent,
            )
            phase_result = await _run_agent_phase(
                agent=phase_agent,
                phase=phase,
                prompt=prompt,
                config=config,
                budget=phase_budget,
                budget_profile=budget_profile,
                research_budget=research_budget,
                run_trace=run_trace,
                remaining_workflow_seconds=remaining_workflow_seconds,
                max_subagent_calls=max_subagent_calls if phase.requires_tools else None,
                emit_final_result=phase.key == "final_report",
            )
            if not phase_result:
                run_trace.degraded = True
                phase_result = build_degraded_phase_output(
                    task_query=task_query,
                    phase=phase,
                    phase_outputs=phase_outputs,
                    reason="phase budget was exhausted before a usable artifact was captured",
                )
                monitor._emit(
                    "phase_degraded",
                    f"Using degraded artifact for phase: {phase.key}",
                    {
                        "phase_key": phase.key,
                        "phase_title": phase.title,
                        "result_preview": phase_result[:500],
                        "budget_profile": budget_profile,
                    },
                )
                write_audit_event(
                    "research_phase_degraded",
                    {
                        "phase_key": phase.key,
                        "phase_title": phase.title,
                        "result_preview": phase_result[:500],
                        "budget_profile": budget_profile,
                    },
                    thread_id=event_thread_id,
                )
                if phase.key == "final_report":
                    monitor.report_task_result(phase_result)
                    write_audit_event(
                        "task_result",
                        {
                            "result": phase_result,
                            "degraded": True,
                            "budget_profile": budget_profile,
                        },
                        thread_id=event_thread_id,
                    )

            phase_outputs[phase.key] = phase_result
            if phase.key == "final_report":
                final_result = phase_result

        if not final_result:
            fallback_result = phase_outputs.get("evidence_compression") or phase_outputs.get(
                "supervisor_research"
            )
            if fallback_result:
                final_result = (
                    "本轮研究已达到当前执行预算，以下是基于已完成阶段整理的可用结果。\n\n"
                    + fallback_result
                )
                monitor.report_task_result(final_result)
                write_audit_event(
                    "task_result",
                    {
                        "result": final_result,
                        "degraded": True,
                        "budget_profile": budget_profile,
                    },
                    thread_id=event_thread_id,
                )

    except asyncio.CancelledError:
        run_status = "cancelled"
        run_failure_reason = "cancelled_by_user_or_eval"
        monitor.report_task_cancelled()
        write_audit_event("task_cancelled", {}, thread_id=event_thread_id)
        raise
    except TimeoutError:
        run_status = "timeout"
        run_failure_reason = "run_timeout"
        message = (
            "Agent execution exceeded the configured runtime budget. "
            "Increase the phase or hard runtime budget for larger research tasks."
        )
        monitor._emit("error", message)
        write_audit_event(
            "task_timeout",
            {
                "hard_timeout_seconds": research_budget.limits.total_seconds,
                "budget_profile": budget_profile,
            },
            thread_id=event_thread_id,
        )
    except Exception as e:
        if e.__class__.__name__ == "GraphRecursionError":
            run_status = "recursion_limit"
            run_failure_reason = "graph_recursion_limit"
            message = (
                "Agent execution reached the configured recursion budget before a "
                "phase handler could degrade gracefully."
            )
            monitor._emit("error", message)
            write_audit_event(
                "task_recursion_limit",
                {
                    "hard_recursion_limit": settings.agent_hard_max_recursion_limit,
                    "budget_profile": budget_profile,
                    "error": repr(e),
                },
                thread_id=event_thread_id,
            )
            return final_result
        run_status = "error"
        run_failure_reason = e.__class__.__name__
        # 异步执行异常也走 monitor，保证前端能收到明确错误事件
        monitor._emit("error", f"执行主智能发生异常信息：{str(e)}")
        write_audit_event("task_error", {"error": repr(e)}, thread_id=event_thread_id)
    finally:
        trace_payload = run_trace.finalize(
            status=run_status,
            final_result=final_result,
            failure_reason=run_failure_reason,
        )
        trace_path = session_dir / "research_trace.json"
        try:
            ResearchRunTrace.write(trace_path, trace_payload)
            monitor._emit(
                "research_trace_complete",
                "研究运行 Trace 已生成",
                {
                    "path": str(trace_path),
                    "status": trace_payload["status"],
                    "elapsed_ms": trace_payload["elapsed_ms"],
                    "metrics": trace_payload["metrics"],
                    "waste": trace_payload["waste"],
                },
            )
            write_audit_event(
                "research_trace_complete",
                trace_payload,
                thread_id=event_thread_id,
            )
        except Exception as trace_error:
            write_audit_event(
                "research_trace_error",
                {"error": repr(trace_error)},
                thread_id=event_thread_id,
            )
        reset_research_runtime(runtime_tokens)
        # 任务结束后恢复 ContextVar，避免后续请求复用到本次会话目录或 thread_id
        reset_session_context(session_dir_token, session_id_token, user_id_token)

    return final_result


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_deep_agent("从网络查询机器人信息，并生成Markdown文件", "test_session_001"))
