"""Source metadata for reranker inputs; raw Evidence content is never modified."""


def source_context_text(
    content: str, *, filename: str = "", page_start=None, page_end=None, section: str | None = None
) -> str:
    metadata = []
    if filename.strip():
        metadata.append("来源文档：" + filename.strip()[:240])
    if page_start is not None:
        pages = str(page_start)
        if page_end is not None and page_end != page_start:
            pages += "-" + str(page_end)
        metadata.append("页码：" + pages)
    if section and section.strip():
        metadata.append("结构位置：" + section.strip()[:240])
    return "\n".join(metadata) + "\n正文：\n" + content if metadata else content
