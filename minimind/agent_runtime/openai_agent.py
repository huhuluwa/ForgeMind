"""Small OpenAI-compatible tool loop for a localhost model server."""
import json
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from agent_runtime.prompts import forgemind_identity_reply


def _fallback_tool_calls(content, allowed):
    """Read the repository's explicit tool tag or Qwen-style JSON content safely."""
    text = (content or "").strip()
    if text.startswith("<tool_call>") and text.endswith("</tool_call>"):
        text = text[len("<tool_call>"):-len("</tool_call>")].strip()
    elif text.startswith("{{") and text.endswith("}}"):
        text = text[1:-1]
    elif text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
        if "\n" in text and text.split("\n", 1)[0].strip().lower() in {"json", "javascript"}:
            text = text.split("\n", 1)[1].strip()
    try:
        data = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict) or set(data) != {"name", "arguments"}:
        return []
    if data["name"] not in allowed or not isinstance(data["arguments"], dict):
        return []
    return [{"id": f"call-{uuid.uuid4().hex}", "type": "function",
             "function": {"name": data["name"], "arguments": data["arguments"]}}]


def run_agent(api_base, model, messages, tools, execute_tool, workspace, system_prompt,
              max_tokens=1024, temperature=0.0, max_tool_rounds=4, timeout=600):
    identity_answer = forgemind_identity_reply(messages)
    if identity_answer:
        return {"id": f"chatcmpl-{uuid.uuid4().hex}", "object": "chat.completion",
                "created": int(time.time()), "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": identity_answer},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "agent_metrics": {"tool_calls": [], "successful_changes": 0,
                                  "latency_seconds": 0.0}}
    conversation = [dict(message) for message in messages]
    if not any(message.get("role") == "system" for message in conversation):
        conversation.insert(0, {"role": "system", "content": system_prompt})
    endpoint = api_base.rstrip("/") + "/chat/completions"
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    trace = []
    changed = 0
    started = time.perf_counter()
    allowed = {tool["function"]["name"] for tool in tools}
    for turn in range(max(0, min(int(max_tool_rounds), 6)) + 1):
        payload = {"model": model, "messages": conversation, "tools": tools,
                   "tool_choice": "auto", "parallel_tool_calls": False,
                   "max_tokens": max(1, min(int(max_tokens), 2048)),
                   "temperature": max(0.0, min(float(temperature), 2.0)),
                   "stream": False, "chat_template_kwargs": {"enable_thinking": False}}
        request = Request(endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read(4_000_000).decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            detail = ""
            if isinstance(exc, HTTPError):
                detail = exc.read(1200).decode("utf-8", "replace")
            raise RuntimeError(f"Local model API failed: {type(exc).__name__} {detail[:1200]}") from exc
        usage = result.get("usage") or {}
        for key in totals:
            totals[key] += int(usage.get(key, 0) or 0)
        choice = result.get("choices", [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        calls = message.get("tool_calls") or _fallback_tool_calls(content, allowed)
        if not calls:
            return {"id": f"chatcmpl-{uuid.uuid4().hex}", "object": "chat.completion",
                    "created": int(time.time()), "model": model,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                                 "finish_reason": choice.get("finish_reason", "stop")}],
                    "usage": totals, "agent_metrics": {"tool_calls": trace,
                    "successful_changes": changed, "latency_seconds": round(time.perf_counter()-started, 3)}}
        if turn >= max_tool_rounds:
            content = message.get("content") or "工具调用轮数已用完；请缩小任务范围后重试。"
            return {"id": f"chatcmpl-{uuid.uuid4().hex}", "object": "chat.completion",
                    "created": int(time.time()), "model": model,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                                 "finish_reason": "length"}], "usage": totals,
                    "agent_metrics": {"tool_calls": trace, "successful_changes": changed,
                                      "latency_seconds": round(time.perf_counter()-started, 3)}}
        conversation.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": calls})
        for call in calls:
            function = call.get("function") or {}
            name = function.get("name", "")
            arguments = function.get("arguments", {})
            if name not in allowed:
                tool_result = {"error": f"Tool not allowed: {name}"}
            else:
                tool_result = execute_tool(name, arguments, workspace)
            if isinstance(tool_result, dict) and tool_result.get("applied") is True:
                changed += 1
            if isinstance(tool_result, dict):
                summary = {key: tool_result[key] for key in ("applied", "error", "files", "detail", "sources", "provider") if key in tool_result}
            else:
                summary = {"error": "Invalid tool result"}
            trace.append({"name": name, "arguments": arguments, "result": summary})
            conversation.append({"role": "tool", "tool_call_id": call.get("id", ""),
                                 "content": json.dumps(tool_result, ensure_ascii=False)[:12000]})
    raise RuntimeError("Agent loop ended without a final response")
