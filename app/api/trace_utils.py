"""Helpers for converting monitor traces into persisted chat metadata."""


def trace_files(events: list[dict]) -> list[dict]:
    files: dict[str, dict] = {}
    for event in events:
        if event.get("event") != "file_created":
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        path = data.get("path")
        name = data.get("name")
        size = data.get("size")
        mtime = data.get("mtime")
        if not (
            isinstance(path, str)
            and isinstance(name, str)
            and isinstance(size, (int, float))
            and isinstance(mtime, (int, float))
        ):
            continue
        files[path] = {
            "name": name,
            "type": data.get("type") if isinstance(data.get("type"), str) else "file",
            "path": path,
            "size": size,
            "mtime": mtime,
        }
    return sorted(files.values(), key=lambda item: item.get("mtime", 0), reverse=True)


def trace_result(events: list[dict]) -> str:
    for event in reversed(events):
        if event.get("event") != "task_result":
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        result = data.get("result")
        if isinstance(result, str) and result.strip():
            return result
    return ""


def trace_terminal_message(events: list[dict]) -> str:
    for event in reversed(events):
        if event.get("event") in {"error", "task_cancelled"}:
            message = event.get("message")
            if isinstance(message, str) and message.strip():
                return message
    return ""
