"""Claude agent loop with streaming and tool dispatch."""
import json
from pathlib import Path

import anthropic

from app.config import settings
from app.chat.tools import get_tools
from app.chat.stream import sse_text, sse_tool_status, sse_image, sse_file, sse_error, sse_done
from app.chat.code_executor import execute_python, execute_node, read_skill_docs
from app.database.duckdb_manager import execute_query
from app.chat.rag import search_documents

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 8192
MAX_TOOL_ROUNDS = 12

PROMPTS_DIR = Path(__file__).parent.parent / "system_prompts"


def load_system_prompt() -> str:
    base = (PROMPTS_DIR / "base.txt").read_text(encoding="utf-8")
    schema = (PROMPTS_DIR / "database_schemas" / "meridian.txt").read_text(encoding="utf-8")
    return f"{base}\n\n{schema}"


def _execute_tool(name: str, tool_input: dict) -> str:
    if name == "query_database":
        result = execute_query(tool_input["sql"], tool_input.get("system", "salesforce"))
        return json.dumps(result, default=str)
    if name == "run_python":
        result = execute_python(tool_input["code"])
        return json.dumps(result, default=str)
    if name == "run_node":
        result = execute_node(tool_input["code"])
        return json.dumps(result, default=str)
    if name == "read_skill_docs":
        result = read_skill_docs(tool_input["skill"])
        return json.dumps(result, default=str)
    if name == "search_documents":
        result = search_documents(tool_input["query"])
        return json.dumps(result, default=str)
    return json.dumps({"error": f"Unknown tool: {name}"})


# Tools that produce files and charts
_CODE_TOOLS = {"run_python", "run_node"}

# Status messages per tool
_TOOL_STATUS = {
    "run_python": "Running Python code...",
    "run_node": "Running Node.js code...",
    "read_skill_docs": "Loading API docs...",
    "search_documents": "Searching corporate documents...",
}


def _run_agent_sync(
    message: str,
    history: list[dict],
    user_id: int,
):
    """Synchronous generator that runs the Claude agent loop, yielding SSE events."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    system_prompt = load_system_prompt()
    tools = get_tools()

    messages = list(history)
    messages.append({"role": "user", "content": message})

    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_read = 0

    try:
        for _round in range(MAX_TOOL_ROUNDS):
            with client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                messages=messages,
                tools=tools,
            ) as stream:
                for event in stream:
                    if event.type == "content_block_delta":
                        if hasattr(event.delta, "type"):
                            if event.delta.type == "text_delta":
                                yield sse_text(event.delta.text)

                response = stream.get_final_message()

            # Track usage
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens
            if hasattr(response.usage, "cache_read_input_tokens"):
                total_cache_read += response.usage.cache_read_input_tokens or 0

            # If no tool use, we're done
            if response.stop_reason != "tool_use":
                break

            # Process tool calls
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    # Show status
                    if block.name == "query_database":
                        system_name = block.input.get("system", "database") if isinstance(block.input, dict) else "database"
                        yield sse_tool_status(f"Querying {system_name}...")
                    elif block.name in _TOOL_STATUS:
                        yield sse_tool_status(_TOOL_STATUS[block.name])

                    # Execute the tool
                    result_str = _execute_tool(block.name, block.input)

                    # For code tools, emit charts and file links
                    if block.name in _CODE_TOOLS:
                        result_data = json.loads(result_str)
                        for chart_b64 in result_data.get("charts", []):
                            yield sse_image(chart_b64)
                        for file_info in result_data.get("files", []):
                            yield sse_file(file_info["filename"], file_info["url"])

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

    except anthropic.APIError as e:
        yield sse_error(f"API error: {e.message}")
    except Exception as e:
        yield sse_error(f"Error: {str(e)}")

    # Log usage
    if total_input_tokens > 0:
        from app.database.user_db import log_usage
        cost_cents = (
            (total_input_tokens - total_cache_read) * 3.0 / 10000
            + total_cache_read * 0.3 / 10000
            + total_output_tokens * 15.0 / 10000
        )
        log_usage(
            user_id=user_id,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            cache_read_tokens=total_cache_read,
            model=MODEL,
            cost_cents=cost_cents,
        )

    yield sse_done()


def run_agent(
    message: str,
    history: list[dict],
    user_id: int,
):
    """Run the agent, returning a sync generator of SSE events."""
    return _run_agent_sync(message, history, user_id)
