#!/usr/bin/env python3
"""Small local deployment smoke check for the ForgeMind portable package."""
from __future__ import annotations

import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

WEB = "http://127.0.0.1:8094"
API = "http://127.0.0.1:8091/v1"
MODEL = "forgemind-qwen25-coder-7b"


def get_json(url: str, timeout: int = 5) -> dict:
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    try:
        health = get_json(f"{WEB}/healthz")
        checks.append(("网页健康", health.get("status") == "ok", str(health)))
    except Exception as exc:
        checks.append(("网页健康", False, repr(exc)))

    try:
        model_data = get_json(f"{API}/models")
        ids = [item.get("id") for item in model_data.get("data", [])]
        checks.append(("模型 API", MODEL in ids, ", ".join(str(item) for item in ids)))
    except Exception as exc:
        checks.append(("模型 API", False, repr(exc)))

    try:
        payload = json.dumps({
            "model": MODEL,
            "messages": [{"role": "user", "content": "请只回复：部署自检通过"}],
            "max_tokens": 48,
            "temperature": 0,
        }).encode("utf-8")
        request = Request(
            f"{API}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
        answer = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        checks.append(("聊天生成", bool(answer.strip()), answer.strip().replace("\n", " ")[:180]))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        checks.append(("聊天生成", False, f"HTTP {exc.code}: {detail}"))
    except (URLError, TimeoutError, Exception) as exc:
        checks.append(("聊天生成", False, repr(exc)))

    for name, passed, detail in checks:
        print(f"{'PASS' if passed else 'FAIL'} | {name} | {detail}")
    if all(passed for _, passed, _ in checks):
        print("ForgeMind 部署自检全部通过。")
        return 0
    print("ForgeMind 部署自检未全部通过；请检查 README 常见问题与 logs/。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
