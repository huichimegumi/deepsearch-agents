"""
主智能体组装与异步执行模块

负责把模型、主提示词、文件类工具和三个专家子智能体组装成 DeepAgent，
并提供 run_deep_agent 作为后续 API 层调用的统一入口。运行时还会为每个
session_id 创建独立工作目录，并把工具调用、子智能体调用和最终结果推送给前端。
"""

import asyncio
import shutil
from functools import lru_cache
from pathlib import Path

from deepagents import create_deep_agent

from app.agent.llm import get_model
from app.agent.prompts import main_agent_content
from app.agent.subagents.database_query_agent import database_query_agent
from app.agent.subagents.knowledge_base_agent import knowledge_base_agent
from app.agent.subagents.network_search_agent import network_search_agent
from app.api.audit import write_audit_event
from app.api.context import (
    reset_session_context,
    set_session_context,
    set_thread_context,
    set_user_context,
)
from app.api.monitor import monitor
from app.memory.checkpoint import get_short_term_checkpointer
from app.memory.service import format_memories_for_prompt, search_memories

# 文件类工具由主智能体直接掌握，负责读取上传附件和生成最终交付文档
from app.tools.markdown_tools import generate_markdown
from app.tools.memory_tools import remember_user_memory, search_user_memory
from app.tools.pdf_tools import convert_md_to_pdf
from app.tools.upload_file_read_tool import read_file_content


@lru_cache(maxsize=1)
def get_main_agent():
    """Build the agent graph on first use after configuration is validated."""
    return create_deep_agent(
        model=get_model(),
        system_prompt=main_agent_content["system_prompt"],
        tools=[
            generate_markdown,
            convert_md_to_pdf,
            read_file_content,
            remember_user_memory,
            search_user_memory,
        ],
        checkpointer=get_short_term_checkpointer(),
        subagents=[database_query_agent, network_search_agent, knowledge_base_agent],
    )


# 当前文件位于 app/agent/main_agent.py，parents[1] 即 app 目录
project_root_path = Path(__file__).parents[1].resolve()


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


async def run_deep_agent(
    task_query,
    session_id,
    user_id: str | None = None,
    monitor_thread_id: str | None = None,
    conversation_memory: str = "",
):
    """
    异步流式执行主智能体

    API 层会为每次任务传入用户问题和 session_id。本函数负责准备会话目录、
    复制上传文件、写入 ContextVar，并在流式执行过程中把关键事件上报给前端。
    :param task_query: 前端提交的原始任务问题
    :param session_id: 当前任务 ID，同时用于 thread_id、输出目录和 WebSocket 定向推送
    """
    event_thread_id = monitor_thread_id or session_id
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

    # 前端拿到工作目录后，可以展示本次任务生成的 Markdown/PDF 等产物
    monitor.report_session_dir(session_dir_str)

    # checkpointer 依赖 thread_id 区分会话记忆；同一 session_id 会复用同一条执行上下文
    config = {"configurable": {"thread_id": event_thread_id}}

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
    try:
        main_agent = get_main_agent()
        # astream 会持续产出模型节点、工具节点和子智能体节点的状态片段
        async for chunk in main_agent.astream(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            task_query
                            + path_instruction
                            + source_routing_instruction
                            + memory_instruction
                            + ("\n\n" + conversation_memory if conversation_memory else "")
                        ),
                    }
                ]
            },
            config=config,
        ):
            # chunk 形如 {"model": {"messages": [...]}}，这里主要关心模型最新消息
            for node_name, state in chunk.items():
                if not state or "messages" not in state:
                    continue
                messages = state["messages"]
                if messages and isinstance(messages, list):
                    last_msg = messages[-1]
                    if node_name == "model":
                        if last_msg.tool_calls:
                            # DeepAgents 调用子智能体时，本质上会产生名为 task 的工具调用
                            for tool_call in last_msg.tool_calls:
                                if tool_call["name"] == "task":
                                    # 子智能体调用单独上报，前端可以展示“正在调用哪个专家助手”
                                    monitor.report_assistant(
                                        tool_call["args"]["subagent_type"],
                                        {"description": tool_call["args"]["description"]},
                                    )
                        elif last_msg.content:
                            # 模型没有继续调用工具时，最新文本内容就是本轮可反馈给前端的结果
                            print(f"主智能体执行结果，最终结果：{last_msg.content[:100]}")
                            monitor.report_task_result(last_msg.content)
                            final_result = last_msg.content
                            write_audit_event(
                                "task_result",
                                {"result": last_msg.content},
                                thread_id=event_thread_id,
                            )

    except asyncio.CancelledError:
        monitor.report_task_cancelled()
        write_audit_event("task_cancelled", {}, thread_id=event_thread_id)
        raise
    except Exception as e:
        # 异步执行异常也走 monitor，保证前端能收到明确错误事件
        monitor._emit("error", f"执行主智能发生异常信息：{str(e)}")
        write_audit_event("task_error", {"error": repr(e)}, thread_id=event_thread_id)
    finally:
        # 任务结束后恢复 ContextVar，避免后续请求复用到本次会话目录或 thread_id
        reset_session_context(session_dir_token, session_id_token, user_id_token)

    return final_result


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_deep_agent("从网络查询机器人信息，并生成Markdown文件", "test_session_001"))
