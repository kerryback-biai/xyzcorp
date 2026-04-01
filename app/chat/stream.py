"""SSE event formatting helpers."""
import json


def sse_event(event_type: str, data: dict | str) -> str:
    if isinstance(data, str):
        payload = json.dumps({"type": event_type, "content": data})
    else:
        payload = json.dumps({"type": event_type, **data})
    return f"data: {payload}\n\n"


def sse_text(text: str) -> str:
    return sse_event("text", text)


def sse_tool_status(message: str) -> str:
    return sse_event("tool_status", {"message": message})


def sse_image(base64_data: str) -> str:
    return sse_event("image", {"data": base64_data})


def sse_file(filename: str, url: str) -> str:
    return sse_event("file", {"filename": filename, "url": url})


def sse_error(message: str) -> str:
    return sse_event("error", {"message": message})


def sse_done() -> str:
    return "data: [DONE]\n\n"
