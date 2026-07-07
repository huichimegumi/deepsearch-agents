"""
Deterministic deep-research workflow scaffolding.

The LLM still decides how to search and synthesize, but the backend owns the
phase order so final answers cannot skip the brief, evidence gathering, and
compression gates.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchPhase:
    """A single backend-enforced research phase."""

    key: str
    title: str
    instruction: str
    requires_tools: bool = False


RESEARCH_PHASES = (
    ResearchPhase(
        key="clarify_and_brief",
        title="澄清问题与研究简报",
        instruction="""
【阶段 1/4：澄清问题与研究简报】
目标：把用户问题转化为可执行 research brief。此阶段只做任务理解和计划，不生成最终答案。

必须输出：
1. 用户真正要回答的问题
2. 已知约束、时间范围、地域/行业范围、输出格式要求
3. 若问题存在歧义，列出需要澄清的问题；若用户不在线，写明本轮继续执行所采用的合理假设
4. 信息源计划：本地知识库、数据库、网络搜索、上传附件分别是否需要使用，以及原因
5. 研究分工：准备派发给各 researcher/子智能体的子问题

禁止：
- 禁止调用 generate_markdown 或 convert_md_to_pdf
- 禁止给出最终结论
""".strip(),
    ),
    ResearchPhase(
        key="supervisor_research",
        title="Supervisor 分派与 researcher 循环",
        instruction="""
【阶段 2/4：Supervisor 分派与 researcher 循环】
目标：根据 research brief 分派子智能体，完成检索、核验和反思。

必须执行：
1. 按 brief 调用合适的子智能体或文件读取工具获取证据
2. 复杂问题至少覆盖 2 个互补角度；若证据不足，进行 1 次有针对性的追问/补检索
3. 对关键结论记录来源、URL/文件名/页码/SQL 结果等可追溯信息
4. 明确列出证据缺口、冲突和可信度限制

必须输出：
- Evidence Ledger：按“结论候选 / 证据 / 来源 / 可信度 / 缺口”整理
- Reflection：还缺什么、是否需要补检索、为什么可以停止

禁止：
- 禁止调用 generate_markdown 或 convert_md_to_pdf
- 禁止在证据不足时假装已完成核验
""".strip(),
        requires_tools=True,
    ),
    ResearchPhase(
        key="evidence_compression",
        title="证据压缩",
        instruction="""
【阶段 3/4：证据压缩】
目标：把 researcher 返回的大量材料压缩成最终报告可直接引用的证据包。

必须输出：
1. 核心结论列表：每条结论都绑定证据和来源
2. 引用清单：保留 URL、文件名、页码、表名或 SQL 摘要等来源标识
3. 冲突信息：不同来源不一致时保留分歧，不要强行抹平
4. 不确定性与边界：哪些结论只能作为推断，哪些数据缺失
5. 最终报告结构建议

禁止：
- 禁止调用 generate_markdown 或 convert_md_to_pdf
- 禁止丢弃来源信息
""".strip(),
    ),
    ResearchPhase(
        key="final_report",
        title="最终报告",
        instruction="""
【阶段 4/4：最终报告】
目标：只基于前面阶段的 research brief、Evidence Ledger 和压缩证据生成最终回答或交付文档。

必须执行：
1. 先回答用户最关心的结论，再展开依据
2. 所有关键信息尽量带来源；无法确认的内容明确标注不确定性
3. 若用户要求 Markdown/PDF 等文件，此阶段才可以调用 generate_markdown / convert_md_to_pdf
4. 若生成文件，内容必须来自已压缩证据包，不得写入“等待子任务完成”等占位内容

输出要求：
- 未要求文件时，直接给出结构化最终答案
- 要求文件时，先生成文件，再用简短文字说明已完成
""".strip(),
    ),
)


def format_previous_phase_outputs(phase_outputs: dict[str, str]) -> str:
    """Format completed phase outputs for the next phase prompt."""
    if not phase_outputs:
        return ""

    blocks = ["【已完成阶段产物】"]
    for phase in RESEARCH_PHASES:
        output = phase_outputs.get(phase.key)
        if output:
            blocks.append(f"\n## {phase.title}\n{output}")
    return "\n".join(blocks)


def build_degraded_phase_output(
    *,
    task_query: str,
    phase: ResearchPhase,
    phase_outputs: dict[str, str],
    reason: str,
) -> str:
    """Build a deterministic fallback artifact when a phase exhausts its budget."""
    previous_keys = ", ".join(phase_outputs.keys()) or "none"
    if phase.key == "clarify_and_brief":
        return "\n".join(
            [
                "## Degraded Research Brief",
                f"- Original task: {task_query}",
                f"- Degradation reason: {reason}",
                "- Working assumption: continue with the user's original request as stated.",
                "- Source plan: use local files, knowledge base, database, and web search only "
                "when relevant to the original task.",
                "- Required next step: gather evidence and explicitly record gaps because the "
                "normal clarification brief did not complete.",
            ]
        )
    if phase.key == "supervisor_research":
        return "\n".join(
            [
                "## Degraded Evidence Ledger",
                f"- Original task: {task_query}",
                f"- Degradation reason: {reason}",
                f"- Prior phase artifacts available: {previous_keys}",
                "- Evidence status: no complete supervisor evidence ledger was produced before "
                "the phase budget was exhausted.",
                "- Gap: final synthesis must clearly mark unsupported claims and avoid inventing "
                "citations.",
            ]
        )
    if phase.key == "evidence_compression":
        return "\n".join(
            [
                "## Degraded Evidence Package",
                f"- Original task: {task_query}",
                f"- Degradation reason: {reason}",
                f"- Prior phase artifacts available: {previous_keys}",
                "- Compression status: the normal evidence compression phase did not complete.",
                "- Final report constraint: rely only on explicit prior artifacts and label all "
                "missing or uncertain evidence.",
            ]
        )
    return "\n".join(
        [
            "## Budget-Limited Final Answer",
            f"The final report phase could not complete normally: {reason}.",
            "",
            "Available phase artifacts:",
            format_previous_phase_outputs(phase_outputs) or "No completed phase artifacts were captured.",
            "",
            "Because the workflow did not finish, treat this as a partial result and verify any "
            "high-stakes conclusions before using them.",
        ]
    )


def build_phase_prompt(
    *,
    task_query: str,
    phase: ResearchPhase,
    phase_outputs: dict[str, str],
    runtime_instructions: str,
) -> str:
    """Build the user message for one enforced workflow phase."""
    previous = format_previous_phase_outputs(phase_outputs)
    tool_boundary = ""
    if phase.key == "final_report":
        tool_boundary = (
            "FINAL REPORT TOOL BOUNDARY: Do not call researcher subagents, web search, "
            "knowledge-base search, or database query tools in this phase. Write only from "
            "the completed phase artifacts above. If evidence is missing, say so explicitly."
        )
    elif not phase.requires_tools:
        tool_boundary = (
            "NO-TOOL PHASE BOUNDARY: The backend has not provided researcher subagents, "
            "web search, knowledge-base search, database query, or file tools in this phase. "
            "Use only the user request and completed phase artifacts. If evidence is missing, "
            "record it as a gap for the supervisor research phase instead of trying to fetch it."
        )
    else:
        tool_boundary = (
            "RESEARCH PHASE BOUNDARY: This is the only phase where researcher subagents and "
            "evidence-gathering tools are available. Gather enough evidence for the ledger, "
            "then stop and return the ledger plus reflection instead of expanding indefinitely."
        )
    return "\n\n".join(
        part
        for part in (
            f"【用户原始问题】\n{task_query}",
            previous,
            runtime_instructions,
            tool_boundary,
            phase.instruction,
        )
        if part
    )
