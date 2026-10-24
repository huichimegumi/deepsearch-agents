"""Narrow the existing tool name to local retrieval in the indexed-only researcher."""

from langchain_core.tools import tool

from app.tools.evidence_tool import collect_evidence as unified_evidence


@tool("collect_evidence")
async def collect_local_evidence(query: str, knowledge_base: str = "all") -> str:
    """Search already indexed local documents and return actual Evidence IDs.

    This tool only retrieves local documents. It cannot query SQL, calculate fees, search
    the web, list/read/write files, or manage memory. Use a focused retrieval query and an
    exact knowledge-base name when known. Empty/error results do not prove document absence.
    """
    return await unified_evidence.ainvoke(
        {
            "source": "local_document",
            "query": query,
            "knowledge_base": knowledge_base,
        }
    )
