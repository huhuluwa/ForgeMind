"""Strict tool registry; model output never chooses arbitrary commands."""

import json

from agent_runtime.code_tools import propose_patch, read_file, replace_text, run_tests, search_code
from agent_runtime.search import search_web


AGENT_TOOLS = [
    {"type": "function", "function": {"name": "web_search", "description": "Search the live web and return source URLs and dated snippets.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "search_code", "description": "Find a literal string in text files inside the configured repository.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "Read one text file inside the configured repository.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "propose_patch", "description": "Apply a unified diff inside the configured repository. Disabled unless the operator enables code writes.", "parameters": {"type": "object", "properties": {"patch": {"type": "string"}}, "required": ["patch"]}}},
    {"type": "function", "function": {"name": "replace_text", "description": "Replace one exact unique text block in a workspace file; useful for a small focused edit. Disabled unless code writes are enabled.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}}},
    {"type": "function", "function": {"name": "run_tests", "description": "Run pytest in a network-isolated, read-only Docker container when enabled.", "parameters": {"type": "object", "properties": {"test_path": {"type": "string"}}, "required": []}}},
]


def execute_tool(name, arguments, workspace):
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return {"error": "Tool arguments are not valid JSON."}
    if not isinstance(arguments, dict):
        return {"error": "Tool arguments must be a JSON object."}
    try:
        if name == "web_search":
            return search_web(arguments.get("query", ""), arguments.get("max_results", 5))
        if name == "search_code":
            return search_code(workspace, arguments.get("query", ""))
        if name == "read_file":
            return read_file(workspace, arguments.get("path", ""))
        if name == "propose_patch":
            return propose_patch(workspace, arguments.get("patch", ""))
        if name == "replace_text":
            return replace_text(workspace, arguments.get("path", ""), arguments.get("old_text", ""), arguments.get("new_text", ""))
        if name == "run_tests":
            return run_tests(workspace, arguments.get("test_path", "."))
    except (TypeError, ValueError) as exc:
        return {"error": str(exc)}
    return {"error": f"Tool not allowed: {name}"}
