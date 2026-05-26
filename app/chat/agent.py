"""Claude agent loop with streaming and tool dispatch."""
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path

import anthropic

logger = logging.getLogger(__name__)

from app.config import settings
from app.chat.tools import get_tools
from app.chat.stream import sse_text, sse_tool_status, sse_image, sse_file, sse_error, sse_done
from app.chat.code_executor import execute_python, execute_node, read_skill_docs
from app.database.duckdb_manager import execute_query
from app.chat.rag import search_documents

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192
MAX_TOOL_ROUNDS = 12
MAX_HISTORY_CHARS = 100_000  # Trim history if it exceeds this

PROMPTS_DIR = Path(__file__).parent.parent / "system_prompts"


def _trim_history(history: list[dict]) -> list[dict]:
    """Keep only the most recent messages that fit within MAX_HISTORY_CHARS."""
    total = 0
    cutoff = len(history)
    for i in range(len(history) - 1, -1, -1):
        size = len(json.dumps(history[i], default=str))
        total += size
        if total > MAX_HISTORY_CHARS:
            cutoff = i + 1
            break
    return list(history[cutoff:])


def load_system_prompt() -> str:
    base = (PROMPTS_DIR / "base.txt").read_text(encoding="utf-8")
    schema = (PROMPTS_DIR / "database_schemas" / "meridian.txt").read_text(encoding="utf-8")
    return f"{base}\n\n{schema}"


def _execute_tool(name: str, tool_input: dict) -> tuple[str, dict]:
    """Execute a tool and return (result_for_claude, raw_result).

    result_for_claude has large payloads (base64 charts) stripped to stay
    within the Claude context window.  raw_result is the unmodified dict
    so callers can still stream images/files to the user.
    """
    if name == "query_database":
        result = execute_query(tool_input["sql"], tool_input.get("system", "salesforce"))
        return json.dumps(result, default=str), result
    if name in ("run_python", "run_node"):
        if name == "run_python":
            result = execute_python(tool_input["code"])
        else:
            result = execute_node(tool_input["code"])
        # Strip base64 charts from the version sent back to Claude
        # (they're already streamed to the user separately)
        claude_result = {
            **result,
            "charts": [f"<chart {i+1} displayed to user>" for i in range(len(result.get("charts", [])))],
        }
        return json.dumps(claude_result, default=str), result
    if name == "read_skill_docs":
        result = read_skill_docs(tool_input["skill"])
        return json.dumps(result, default=str), result
    if name == "search_documents":
        result = search_documents(tool_input["query"])
        return json.dumps(result, default=str), result
    err = json.dumps({"error": f"Unknown tool: {name}"})
    return err, {}


# Tools that produce files and charts
_CODE_TOOLS = {"run_python", "run_node"}

# Status messages per tool
_TOOL_STATUS = {
    "run_python": "Running Python code...",
    "run_node": "Running Node.js code...",
    "read_skill_docs": "Loading API docs...",
    "search_documents": "Searching corporate documents...",
}

SSE_KEEPALIVE = ": keepalive\n\n"
KEEPALIVE_INTERVAL = 10  # seconds


def _execute_tool_with_keepalive(name: str, tool_input: dict):
    """Run a tool in a thread, yielding (keepalive, None) while waiting,
    then (None, result) when done."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future: Future = executor.submit(_execute_tool, name, tool_input)
        while True:
            try:
                result = future.result(timeout=KEEPALIVE_INTERVAL)
                yield None, result
                return
            except TimeoutError:
                yield SSE_KEEPALIVE, None


def _run_agent_sync(
    message: str,
    history: list[dict],
    user_id: int,
):
    """Synchronous generator that runs the Claude agent loop, yielding SSE events."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    system_prompt = load_system_prompt()
    tools = get_tools()

    messages = _trim_history(history)
    messages.append({"role": "user", "content": message})

    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_read = 0

    request_start = time.time()
    logger.info("Agent request started")

    try:
        for _round in range(MAX_TOOL_ROUNDS):
            round_start = time.time()
            logger.info(f"Round {_round + 1}/{MAX_TOOL_ROUNDS}: calling Claude API")

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

            api_elapsed = time.time() - round_start
            logger.info(f"Round {_round + 1}: Claude API completed in {api_elapsed:.1f}s, stop_reason={response.stop_reason}")

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
                    logger.info(f"Round {_round + 1}: executing tool {block.name}")
                    tool_start = time.time()

                    # Show status
                    if block.name == "query_database":
                        system_name = block.input.get("system", "database") if isinstance(block.input, dict) else "database"
                        yield sse_tool_status(f"Querying {system_name}...")
                    elif block.name in _TOOL_STATUS:
                        yield sse_tool_status(_TOOL_STATUS[block.name])

                    # Execute the tool (with keepalives to prevent proxy timeout)
                    result_str, raw_result = None, None
                    for keepalive, result in _execute_tool_with_keepalive(block.name, block.input):
                        if keepalive is not None:
                            yield keepalive
                        if result is not None:
                            result_str, raw_result = result

                    tool_elapsed = time.time() - tool_start
                    logger.info(f"Round {_round + 1}: tool {block.name} completed in {tool_elapsed:.1f}s")

                    # For code tools, emit charts and file links
                    if block.name in _CODE_TOOLS:
                        for chart_b64 in raw_result.get("charts", []):
                            yield sse_image(chart_b64)
                        for file_info in raw_result.get("files", []):
                            yield sse_file(file_info["filename"], file_info["url"])

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

    except anthropic.APIError as e:
        logger.error(f"API error after {time.time() - request_start:.1f}s: {e.message}")
        yield sse_error(f"API error: {e.message}")
    except Exception as e:
        logger.error(f"Error after {time.time() - request_start:.1f}s: {e}", exc_info=True)
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

    total_elapsed = time.time() - request_start
    logger.info(f"Agent request completed in {total_elapsed:.1f}s (in={total_input_tokens}, out={total_output_tokens})")

    yield sse_done()


def run_agent(
    message: str,
    history: list[dict],
    user_id: int,
):
    """Run the agent, returning a sync generator of SSE events."""
    return _run_agent_sync(message, history, user_id)
