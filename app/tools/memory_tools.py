"""DeepAgents tools for explicit user memory operations."""

from langchain_core.tools import tool

from app.api.context import get_thread_context, get_user_context
from app.memory.service import create_memory, format_memories_for_prompt, search_memories


@tool
def remember_user_memory(content: str, memory_type: str = "fact") -> str:
    """
    Save a durable user memory when the user explicitly asks to remember something.

    :param content: The durable fact, preference or instruction to remember.
    :param memory_type: fact, preference, project, instruction or summary.
    """
    user_id = get_user_context()
    if not user_id:
        return "无法保存记忆：当前请求没有用户上下文。"
    try:
        memory = create_memory(
            user_id=user_id,
            thread_id=get_thread_context(),
            content=content,
            memory_type=memory_type,
            confidence=0.95,
            metadata={"source": "explicit_tool"},
        )
    except Exception as exc:
        return f"保存记忆失败：{exc}"
    return f"已保存记忆：{memory.summary}"


@tool
def search_user_memory(query: str) -> str:
    """
    Search the current user's durable memories when prior preferences or project context may help.

    :param query: Search query for user memory.
    """
    user_id = get_user_context()
    if not user_id:
        return "无法检索记忆：当前请求没有用户上下文。"
    hits = search_memories(user_id=user_id, query=query)
    if not hits:
        return "没有找到相关长期记忆。"
    return format_memories_for_prompt(hits)
