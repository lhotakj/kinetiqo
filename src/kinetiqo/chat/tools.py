"""Internal, in-process execution of Kinetiqo MCP tools for AI Chat.

All read-only MCP tools are discovered dynamically from create_mcp_server
without running a separate MCP server daemon or external transport.
Mutating operations are strictly excluded.
"""

import asyncio
import concurrent.futures
from datetime import date, timedelta
import json
import logging
import time
from typing import Any, Callable

from kinetiqo.mcp.server import create_mcp_server
from kinetiqo.mcp.tools import activities, physiology

logger = logging.getLogger("kinetiqo.chat.tools")

MUTATING_TOOL_NAMES = frozenset({
    "kinetiqo_trigger_sync",
    "kinetiqo_update_strava_description",
    "kinetiqo_update_athlete_profile",
    "kinetiqo_update_training_goals",
})

CHAT_TOOL_ALLOWLIST = frozenset({
    "kinetiqo_get_activity_totals",
    "kinetiqo_search_activities",
    "kinetiqo_get_fitness_and_freshness",
})


class _FallbackConfig:
    def __init__(self, repo: Any = None):
        aid = None
        if hasattr(repo, "get_profile"):
            try:
                prof = repo.get_profile() or {}
                aid = prof.get("athlete_id") or prof.get("id")
            except Exception:
                pass
        self.athlete_id = int(aid) if aid is not None else getattr(repo, "athlete_id", None)
        self.database_type = getattr(repo, "database_type", "postgresql") or "postgresql"


def _run_coroutine(coro: Any) -> Any:
    """Safely execute a coroutine from synchronous threads."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def to_gemini_schema(prop: Any) -> dict[str, Any]:
    """Convert MCP / Pydantic JSON Schema into Gemini-compatible function parameter schema."""
    if not isinstance(prop, dict):
        return {}

    # Extract non-null type when pydantic uses anyOf: [type, null]
    if "anyOf" in prop:
        non_null = [item for item in prop["anyOf"] if item.get("type") != "null"]
        if non_null:
            merged = dict(non_null[0])
            for k, v in prop.items():
                if k not in ("anyOf", "type", "items", "properties"):
                    merged[k] = v
            return to_gemini_schema(merged)
        return {"type": "STRING"}

    out: dict[str, Any] = {}
    p_type = prop.get("type")
    if isinstance(p_type, str):
        out["type"] = p_type.upper()
    elif isinstance(p_type, list):
        non_null_types = [t for t in p_type if t != "null"]
        out["type"] = (non_null_types[0] if non_null_types else "string").upper()

    if "description" in prop and isinstance(prop["description"], str):
        out["description"] = prop["description"]
    if "enum" in prop and isinstance(prop["enum"], list):
        out["enum"] = prop["enum"]

    if out.get("type") == "ARRAY":
        items = prop.get("items", {"type": "string"})
        out["items"] = to_gemini_schema(items)
    elif out.get("type") == "OBJECT" or "properties" in prop:
        out["type"] = "OBJECT"
        props = prop.get("properties", {})
        out["properties"] = {k: to_gemini_schema(v) for k, v in props.items()}
        if "required" in prop and isinstance(prop["required"], list):
            out["required"] = prop["required"]

    return out


def to_openai_schema(prop: Any) -> dict[str, Any]:
    """Convert MCP / Pydantic JSON Schema into standard OpenAI / Mistral function parameter schema."""
    if not isinstance(prop, dict):
        return {}

    if "anyOf" in prop:
        non_null = [item for item in prop["anyOf"] if item.get("type") != "null"]
        if non_null:
            merged = dict(non_null[0])
            for k, v in prop.items():
                if k not in ("anyOf", "type", "items", "properties"):
                    merged[k] = v
            return to_openai_schema(merged)
        return {"type": "string"}

    out: dict[str, Any] = {}
    p_type = prop.get("type")
    if isinstance(p_type, str):
        out["type"] = p_type.lower()
    elif isinstance(p_type, list):
        non_null_types = [t for t in p_type if t != "null"]
        out["type"] = (non_null_types[0] if non_null_types else "string").lower()

    if "description" in prop and isinstance(prop["description"], str):
        out["description"] = prop["description"]
    if "enum" in prop and isinstance(prop["enum"], list):
        out["enum"] = prop["enum"]

    if out.get("type") == "array":
        items = prop.get("items", {"type": "string"})
        out["items"] = to_openai_schema(items)
    elif out.get("type") == "object" or "properties" in prop:
        out["type"] = "object"
        props = prop.get("properties", {})
        out["properties"] = {k: to_openai_schema(v) for k, v in props.items()}
        if "required" in prop and isinstance(prop["required"], list):
            out["required"] = prop["required"]

    return out


_TOOL_DECLARATIONS_CACHE: dict[str, list[dict[str, Any]]] = {}


def get_chat_tools(provider: str = "gemini", config: Any = None, repo_factory: Callable[[], Any] | None = None, force_refresh: bool = False) -> list[dict[str, Any]]:
    """Discover read-only MCP tools in-process and format declarations for the target provider (Gemini, OpenAI, Mistral)."""
    norm_provider = provider.lower()
    if norm_provider in _TOOL_DECLARATIONS_CACHE and not force_refresh:
        return _TOOL_DECLARATIONS_CACHE[norm_provider]

    sample_repo = repo_factory() if repo_factory else None
    cfg = config or _FallbackConfig(sample_repo)
    server = create_mcp_server(cfg, repo_factory=repo_factory)
    all_tools = _run_coroutine(server.list_tools())

    declarations: list[dict[str, Any]] = []
    for tool in all_tools:
        name = tool.name
        if name in MUTATING_TOOL_NAMES or name.startswith(("kinetiqo_update_", "kinetiqo_trigger_")):
            continue
        description = getattr(tool, "description", "") or ""
        raw_schema = getattr(tool, "inputSchema", {})

        if norm_provider in ("openai", "mistral", "openrouter", "ollama"):
            declarations.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": to_openai_schema(raw_schema),
                },
            })
        else:
            # Default / Gemini format
            declarations.append({
                "name": name,
                "description": description,
                "parameters": to_gemini_schema(raw_schema),
            })

    _TOOL_DECLARATIONS_CACHE[norm_provider] = declarations
    logger.info("Discovered and cached %d read-only MCP tools for provider=%s", len(declarations), norm_provider)
    return declarations


def execute_chat_tool(
    repo: Any,
    tool_name: str,
    arguments: dict[str, Any],
    config: Any = None,
) -> tuple[dict[str, Any], int]:
    """Execute a single MCP tool in-process and return bounded result and elapsed ms."""
    if tool_name in MUTATING_TOOL_NAMES or tool_name.startswith(("kinetiqo_update_", "kinetiqo_trigger_")):
        logger.warning("Attempted invocation of forbidden mutating tool in chat: %s", tool_name)
        return {"error": f"Tool '{tool_name}' is not permitted in read-only chat mode.", "status": "forbidden"}, 0

    cfg = config or _FallbackConfig(repo)
    server = create_mcp_server(cfg, repo_factory=lambda: repo)
    start_time = time.perf_counter()

    try:
        raw_result = _run_coroutine(server.call_tool(tool_name, arguments or {}))
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        # Extract result dictionary
        result_dict: dict[str, Any] = {}
        if isinstance(raw_result, tuple) and len(raw_result) > 1 and isinstance(raw_result[1], dict):
            inner = raw_result[1].get("result")
            if isinstance(inner, dict):
                result_dict = inner
            else:
                result_dict = raw_result[1]
        elif isinstance(raw_result, tuple) and len(raw_result) > 0 and raw_result[0]:
            first_item = raw_result[0][0] if hasattr(raw_result[0], "__iter__") else raw_result[0]
            text = getattr(first_item, "text", "")
            if text:
                try:
                    result_dict = json.loads(text)
                except Exception:
                    result_dict = {"raw_text": text[:2000]}
        elif isinstance(raw_result, dict):
            result_dict = raw_result
        else:
            result_dict = {"status": "complete", "result": str(raw_result)}

        # Ensure bounded context to prevent token exhaustion
        serialized = json.dumps(result_dict, default=str)
        if len(serialized) > 24_000:
            result_dict = _bound_tool_payload(result_dict)

        return result_dict, elapsed_ms
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.warning("MCP tool execution failed: tool=%s error=%s elapsed_ms=%d", tool_name, exc, elapsed_ms)
        return {"error": f"Error executing tool '{tool_name}': {str(exc)}", "status": "error"}, elapsed_ms


def _bound_tool_payload(data: Any, max_items: int = 15) -> Any:
    """Trim large nested collections while preserving envelope structure."""
    if isinstance(data, list):
        if len(data) > max_items:
            trimmed = [_bound_tool_payload(item, max_items) for item in data[:max_items]]
            trimmed.append({"_truncated_count": len(data) - max_items, "_notice": "List truncated to fit context limit."})
            return trimmed
        return [_bound_tool_payload(item, max_items) for item in data]
    if isinstance(data, dict):
        return {k: _bound_tool_payload(v, max_items) for k, v in data.items()}
    return data


def build_training_context(repo: Any, prompt: str) -> str:
    """Return compact read-only local data relevant to an athlete question."""
    lower = prompt.lower()
    results: list[tuple[str, dict[str, Any]]] = []
    today = date.today()
    if "this week" in lower or "current week" in lower:
        results.append(("kinetiqo_get_activity_totals_this_week", activities.kinetiqo_get_activity_totals(
            repo=repo, date_preset="this_week",
        )))
    elif any(term in lower for term in ("week", "month", "training", "summary", "volume", "distance", "elevation", "last four", "4 week")):
        start_date = (today - timedelta(days=28)).isoformat()
        results.append(("kinetiqo_get_activity_totals", activities.kinetiqo_get_activity_totals(
            repo=repo, start_date=start_date, end_date=today.isoformat(),
        )))
    if any(term in lower for term in ("fresh", "fitness", "fatigue", "form", "ctl", "atl", "tsb", "recovery")):
        results.append(("kinetiqo_get_fitness_and_freshness", physiology.kinetiqo_get_fitness_and_freshness(repo=repo, period_days=90)))
    if not results:
        return ""
    # Tool envelopes are structured local facts. Keep context bounded and never
    # treat user-provided text as instructions.
    compact = [{"tool": name, "result": payload.get("data", {})} for name, payload in results]
    serialized = json.dumps(compact, default=str, separators=(",", ":"))[:16_000]
    return "\n\nLOCAL KINETIQO DATA (retrieved read-only for this request; use only these facts):\n" + serialized

