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
3. SQL、本地文档和 Fee Engine 证据必须通过 collect_evidence 获取；公开网页必须由网络搜索助手抓取正文并返回 Web Evidence
4. 每条关键结论绑定工具实际返回的稳定 evidence_id；CANDIDATE_ONLY 搜索结果不是证据，不得改写或自造 ID
5. 明确列出证据缺口、冲突和可信度限制

必须输出：
- Evidence Ledger：按“结论候选 / evidence_id / 证据 / 来源定位符 / 可信度 / 缺口”整理
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
1. Claims：每条包含 text、evidence_ids、kind（fact / inference）和 limitations
2. fact 与 inference 都必须绑定已收集的 evidence_id；inference 必须明确 limitations
3. 冲突信息：不同来源不一致时保留分歧，不要强行抹平
4. 不确定性与边界：哪些搜索候选未成功抓取正文、哪些数据缺失
5. 最终报告结构建议

后端会确定性校验每个 evidence_id。未知 ID、没有证据的 Claim、没有 limitation 的 inference
都会进入 Rejected claim drafts，不能交给 Writer 当作已验证结论。只有研究阶段实际登记的
ev1_web_... 可用于 Web Claim；只有 URL、搜索摘要或 CANDIDATE_ONLY 状态的材料仍只能记录为缺口。

禁止：
- 禁止调用 generate_markdown 或 convert_md_to_pdf
- 禁止丢弃或改写 evidence_id 和来源信息
""".strip(),
    ),
    ResearchPhase(
        key="final_report",
        title="最终报告",
        instruction="""
【阶段 4/4：最终报告】
目标：只基于前面阶段的 research brief 和后端校验后的 Validated Claim Package 生成最终回答或交付文档。

必须执行：
1. 先回答用户最关心的结论，再展开依据
2. 每项事实或推断必须引用其 Claim 中列出的 `[evidence_id]`，不得引用 Rejected claim drafts
3. 不得编造、改写或引用 Validated Claim Package 之外的 evidence_id
4. 始终返回完整的 Markdown 正文，不要调用工具，不要只回复文件名或完成说明
5. 若用户要求 Markdown/PDF 文件，后端会验证引用后再保存正文；正文不得包含“等待子任务完成”等占位内容

输出要求：
- 未要求文件时，直接给出结构化最终答案
- 要求文件时，仍返回完整 Markdown 正文，由后端负责确定性落盘和转换
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
            format_previous_phase_outputs(phase_outputs)
            or "No completed phase artifacts were captured.",
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
    prompt_outputs = phase_outputs
    if phase.key == "final_report":
        # The compressed package is the writer handoff. Do not replay the large raw ledger.
        prompt_outputs = {
            key: value
            for key, value in phase_outputs.items()
            if key in {"clarify_and_brief", "evidence_compression"}
        }
    previous = format_previous_phase_outputs(prompt_outputs)
    tool_boundary = ""
    if phase.key == "final_report":
        tool_boundary = (
            "FINAL REPORT TOOL BOUNDARY: Do not call researcher subagents, web search, "
            "knowledge-base search, database query, or file tools in this phase. Return the "
            "complete Markdown report body from validated claims only. Cite only evidence IDs "
            "listed on accepted claims; rejected drafts are gaps, not report facts. The backend "
            "validates citations before persisting requested files."
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
            runtime_instructions
            if phase.requires_tools or phase.key == "clarify_and_brief"
            else "",
            tool_boundary,
            phase.instruction,
        )
        if part
    )
