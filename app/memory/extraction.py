"""LLM-assisted extraction of durable user memories."""

from __future__ import annotations

import json
import re
from typing import Any

from app.memory.service import create_memory, is_safe_to_store, normalize_memory_type

MAX_ITEMS_PER_TURN = 5


def _json_array(text: str) -> list[dict[str, Any]]:
    clean = text.strip()
    match = re.search(r"\[[\s\S]*\]", clean)
    if match:
        clean = match.group(0)
    payload = json.loads(clean)
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def extract_memory_candidates(user_message: str, assistant_message: str) -> list[dict[str, Any]]:
    prompt = f"""
你是一个对话记忆抽取器。请只抽取未来多轮对话仍可能有用、且用户愿意系统记住的信息。

可以抽取:
- 用户明确偏好，例如语言、格式、输出风格、常用交付物。
- 稳定事实，例如用户正在做的项目、行业、研究方向。
- 持续性指令，例如默认生成 PDF、默认引用来源。
- 本轮形成的高层项目摘要。

不要抽取:
- API key、密码、token、隐私证件号、银行卡、一次性验证码。
- 只对当前任务有效的临时细节。
- 模型猜测、未经用户确认的个人敏感信息。
- 助手自己编造的事实。

请返回 JSON 数组，不要包含 Markdown。每项格式:
{{"content":"...", "memory_type":"preference|fact|project|instruction|summary",
"confidence":0.0到1.0}}

用户消息:
{user_message}

助手回复:
{assistant_message[:4000]}
"""
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
        if not text or text in seen or not is_safe_to_store(text):
            continue
        confidence = item.get("confidence", 0.65)
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            confidence_value = 0.65
        if confidence_value < 0.55:
            continue
        seen.add(text)
        candidates.append(
            {
                "content": text,
                "memory_type": normalize_memory_type(str(item.get("memory_type", "fact"))),
                "confidence": max(0.0, min(1.0, confidence_value)),
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
