"""LLM-assisted extraction of durable user memories."""

from __future__ import annotations

import json
import re
from typing import Any

from app.memory.service import create_memory, is_safe_to_store, normalize_memory_type

MAX_ITEMS_PER_TURN = 3
MIN_AUTO_MEMORY_CONFIDENCE = 0.72
AUTO_EXTRACTABLE_TYPES = {"preference", "project", "instruction"}


EXTRACTION_PROMPT_TEMPLATE = """
你是 DeepSearch Agents 的长期记忆抽取器。
You are the long-term memory extractor for DeepSearch Agents.

目标 / Goal:
只抽取未来多轮对话仍然有用、且用户明确表达或强烈暗示愿意系统持续记住的信息。
Extract only information that remains useful across future turns and that the user
explicitly states or strongly implies should persist.

默认只允许抽取三类 / Default extractable categories:
1. preference: 用户明确偏好，例如语言、报告结构、引用方式、输出风格。
   Explicit user preferences such as language, report structure, citation style,
   or output style.
2. project: 长期项目背景，例如正在持续推进的项目、行业、研究方向、课题目标。
   Durable project context such as ongoing projects, industries, research
   directions, or project goals.
3. instruction: 持续性指令，例如“以后默认...”“每次都...”“请记住...”“始终...”
   Standing instructions such as "by default", "always", "remember that", or
   "for future tasks".

不要抽取 / Do not extract:
- API key、密码、token、隐私证件号、银行卡、一次性验证码。
- 只对当前任务有效的临时细节、一次性文件名、临时搜索目标。
- 助手推断、助手建议、未经用户确认的个人敏感信息。
- 普通知识、网页事实、数据库结果、RAG 文档内容；这些属于证据，不是用户记忆。
- 仅来自助手回复、但用户没有确认的结论。
- 模糊的事实或泛泛摘要；除非它清楚描述一个长期项目背景。

输出要求 / Output:
- 只返回 JSON 数组，不要 Markdown。
- 最多 3 条。
- 如果没有可靠记忆，返回 []。
- content 应该是一句话，具体、可执行、无敏感信息。
- memory_type 只能是 preference、project 或 instruction。
- confidence 必须反映确定性；低于 0.72 的候选不要输出。

格式 / Schema:
[
  {{"content":"...", "memory_type":"preference|project|instruction", "confidence":0.72}}
]

用户消息 / User message:
{user_message}

助手回复，仅作上下文参考；不得单独作为记忆来源 / Assistant response for context only:
{assistant_message}
"""


def _json_array(text: str) -> list[dict[str, Any]]:
    clean = text.strip()
    match = re.search(r"\[[\s\S]*\]", clean)
    if match:
        clean = match.group(0)
    payload = json.loads(clean)
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _is_auto_memory_candidate(
    *, content: str, memory_type: str, confidence: float
) -> bool:
    if memory_type not in AUTO_EXTRACTABLE_TYPES:
        return False
    if confidence < MIN_AUTO_MEMORY_CONFIDENCE:
        return False
    return is_safe_to_store(content)


def extract_memory_candidates(user_message: str, assistant_message: str) -> list[dict[str, Any]]:
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        user_message=user_message,
        assistant_message=assistant_message[:4000],
    )
    from app.agent.llm import get_model

    response = get_model().invoke([{"role": "user", "content": prompt}])
    content = getattr(response, "content", str(response))
    try:
        raw_items = _json_array(content)
    except Exception:
        return []

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item.get("content", "")).strip()
        if not text or text in seen:
            continue
        confidence = item.get("confidence", 0.65)
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            confidence_value = 0.65
        memory_type = normalize_memory_type(str(item.get("memory_type", "")))
        confidence_value = max(0.0, min(1.0, confidence_value))
        if not _is_auto_memory_candidate(
            content=text,
            memory_type=memory_type,
            confidence=confidence_value,
        ):
            continue
        seen.add(text)
        candidates.append(
            {
                "content": text,
                "memory_type": memory_type,
                "confidence": confidence_value,
            }
        )
        if len(candidates) >= MAX_ITEMS_PER_TURN:
            break
    return candidates


def extract_and_store_memories(
    *,
    user_id: str,
    thread_id: str,
    user_message: str,
    assistant_message: str,
    source_message_id: str | None = None,
) -> list[str]:
    stored_ids: list[str] = []
    try:
        candidates = extract_memory_candidates(user_message, assistant_message)
    except Exception:
        return stored_ids

    for candidate in candidates:
        try:
            memory = create_memory(
                user_id=user_id,
                thread_id=thread_id,
                source_message_id=source_message_id,
                content=candidate["content"],
                memory_type=candidate["memory_type"],
                confidence=candidate["confidence"],
                metadata={"source": "auto_extraction"},
            )
            stored_ids.append(memory.id)
        except Exception:
            continue
    return stored_ids
