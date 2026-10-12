"""Build a small, license-clean Agent tool-call SFT mix plus a held-out probe set."""

import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = "read_file, search_code, propose_patch, replace_text, run_tests, web_search"
SYSTEM = (
    "你是代码开发 Agent。可用工具名只有：" + ALLOWED + "。需要执行工具时，只返回一个 <tool_call> 标签，"
    "内部为 JSON 对象，含精确 name 和 arguments；不得发明工具名。文件修改前先读取相关源码。"
    "测试工具只能对仓库内测试运行；网页搜索必须给出查询词。"
)

PATHS = [
    "src/cache/store.py", "app/services/users.py", "pkg/http/client.py", "lib/config/loader.py",
    "server/routes/items.py", "src/worker/retry.py", "tests/test_parser.py", "core/metrics.py",
    "modules/auth/session.py", "tools/build_index.py", "src/db/connection.py", "web/api/orders.py",
]
TERMS = [
    "normalize_email", "retry_delay", "parse_timestamp", "cache_key", "validate_payload",
    "load_settings", "build_report", "safe_join", "serialize_record", "is_allowed_host",
    "merge_headers", "format_currency", "event_type", "request_timeout", "max_retries", "user_id",
]
QUERIES = [
    "find every reference to the retry limit", "search for the stale cache invalidation path",
    "locate where request_timeout is read", "find the serializer for API error responses",
    "search for uses of normalize_email", "find code that writes to the session store",
    "locate the event_type aggregation logic", "search for TODO markers in the config loader",
]
PHRASES = [
    "请打开并检查", "先查看这个模块", "读取仓库文件", "请把源码内容读出来",
    "在开始修改前读取", "检查一下文件", "麻烦先查看文件", "打开目标源码",
]


def call(name, arguments):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": name, "arguments": arguments}}
    ]}


def build_train():
    rows = []
    for i in range(600):
        path = PATHS[i % len(PATHS)]
        term = TERMS[(i * 7) % len(TERMS)]
        query = QUERIES[(i * 5) % len(QUERIES)]
        phrase = PHRASES[(i * 3) % len(PHRASES)]
        kind = i % 8
        if kind in (0, 1):
            prompt, target = f"{phrase} `{path}`。", call("read_file", {"path": path})
        elif kind in (2,):
            prompt, target = f"在整个项目中搜索：{query}。", call("search_code", {"query": query})
        elif kind == 3:
            prompt, target = f"请在网页中查找关于 `{term}` 的官方文档，返回来源。", call("web_search", {"query": f"{term} official documentation", "max_results": 5})
        elif kind == 4:
            old = f"DEFAULT_{term.upper()} = 3"
            new = f"DEFAULT_{term.upper()} = 5"
            prompt = f"已读取 `{path}`，现在把唯一文本 `{old}` 改成 `{new}`。请直接精确替换。"
            target = call("replace_text", {"path": path, "old_text": old, "new_text": new})
        elif kind == 5:
            test_path = "tests/test_" + term + ".py"
            prompt, target = f"仓库修改已完成。请运行 `{test_path}` 验证这次改动。", call("run_tests", {"test_path": test_path})
        elif kind == 6:
            old = f"-    return {term}(value)"
            new = f"+    return normalize_{term}(value)"
            patch = (f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
                     f"@@ -1 +1 @@\n{old}\n{new}\n")
            prompt = f"已经读过 `{path}`。请将以下改动应用到仓库：\n{patch}"
            target = call("propose_patch", {"patch": patch})
        else:
            prompt, target = f"请搜索项目中所有 `{term}` 的定义与调用位置。", call("search_code", {"query": term})
        rows.append({"conversations": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
            target,
        ]})
    for i in range(100):
        path = PATHS[(i * 5 + 2) % len(PATHS)]
        constant = TERMS[(i * 3 + 1) % len(TERMS)].upper()
        old, new = str(10 + i), str(20 + i)
        old_text, new_text = f"DEFAULT_{constant} = {old}", f"DEFAULT_{constant} = {new}"
        test_path = f"tests/test_{TERMS[(i * 7) % len(TERMS)]}.py"
        prompt = (f"请修复 `{path}`：把 `{old_text}` 改为 `{new_text}`。先检查源码，"
                  f"再完成精确修改并运行 `{test_path}`。测试通过后给简短结果，不要重复运行测试。")
        read_call = call("read_file", {"path": path})
        read_result = json.dumps({"path": path, "content": old_text + "\n"}, ensure_ascii=False)
        edit_call = call("replace_text", {"path": path, "old_text": old_text, "new_text": new_text})
        edit_result = json.dumps({"applied": True, "path": path, "message": "Patch applied."}, ensure_ascii=False)
        test_call = call("run_tests", {"test_path": test_path})
        test_result = json.dumps({"passed": True, "stdout": "3 passed"}, ensure_ascii=False)
        prefix = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
        rows.extend([
            {"conversations": prefix + [read_call]},
            {"conversations": prefix + [read_call, {"role": "tool", "content": read_result}, edit_call]},
            {"conversations": prefix + [read_call,
                                         {"role": "tool", "content": read_result},
                                         edit_call,
                                         {"role": "tool", "content": edit_result}, test_call]},
            {"conversations": prefix + [read_call,
                                         {"role": "tool", "content": read_result},
                                         edit_call,
                                         {"role": "tool", "content": edit_result},
                                         test_call,
                                         {"role": "tool", "content": test_result},
                                         {"role": "assistant", "content": "已完成修改，隔离测试通过（3 passed）。"}]},
        ])
    return rows


def build_eval():
    cases = []
    path_pool = ["services/billing/invoice.py", "src/pipeline/stages.py", "web/auth/callback.py", "internal/queue/consumer.py",
                 "config/runtime_flags.py", "lib/text/tokenize.py", "api/v3/catalog.py", "jobs/daily_rollup.py"]
    for i, path in enumerate(path_pool):
        cases.append({"id": f"read_{i}", "prompt": f"我需要查看 `{path}` 的实现细节，先把文件读出来。", "expected": {"name": "read_file", "arguments": {"path": path}}})
    searches = ["where the invoice total is rounded", "all callers of resolve_identity", "the fallback for missing locale", "writes to audit_log", "the websocket reconnect delay", "references to MAX_BATCH_SIZE", "the feature flag for v3 catalog", "the daily rollup timezone conversion"]
    for i, query in enumerate(searches):
        cases.append({"id": f"search_{i}", "prompt": f"在仓库中定位：{query}。", "expected": {"name": "search_code", "arguments": {"query": query}}})
    webq = ["Python official datetime timezone guide", "PostgreSQL official JSONB indexing docs", "FastAPI official lifespan events", "Rust official error handling guide", "Pydantic official settings documentation", "HTTP RFC idempotency semantics", "SQLite official transaction docs", "Python official csv module quoting"]
    for i, query in enumerate(webq):
        cases.append({"id": f"web_{i}", "prompt": f"联网查找 `{query}` 的一手官方文档并给出链接。", "expected": {"name": "web_search", "arguments": {"query": query, "max_results": 5}}})
    for i, path in enumerate(path_pool):
        old, new = f"CACHE_TTL = {17 + i}", f"CACHE_TTL = {27 + i}"
        cases.append({"id": f"replace_{i}", "prompt": f"已经检查过 `{path}`。把唯一一行 `{old}` 精确替换为 `{new}`，不要改其他内容。", "expected": {"name": "replace_text", "arguments": {"path": path, "old_text": old, "new_text": new}}})
    for i in range(8):
        test_path = f"tests/integration/test_release_gate_{i}.py"
        cases.append({"id": f"test_{i}", "prompt": f"改动完成。请通过隔离测试运行器执行 `{test_path}`。", "expected": {"name": "run_tests", "arguments": {"test_path": test_path}}})
    for i, path in enumerate(path_pool):
        patch = (f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
                 "@@ -1 +1 @@\n-    return legacy_mode\n+    return strict_mode\n")
        cases.append({"id": f"patch_{i}", "prompt": f"请应用这个补丁到已读取的仓库：\n{patch}", "expected": {"name": "propose_patch", "arguments": {"patch": patch}}})
    return cases


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    rng = random.Random(20261011)
    train = build_train()
    rng.shuffle(train)
    data_path = ROOT / "dataset" / "forge_agent_tools_1000_v2.jsonl"
    with data_path.open("w", encoding="utf-8", newline="\n") as f:
        for row in train:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    evaluation = {"suite": "forge_agent_toolcalls_v1", "cases": build_eval()}
    eval_path = ROOT / "eval" / "agent_toolcall_holdout_v1.json"
    eval_path.write_text(json.dumps(evaluation, ensure_ascii=False, indent=2), encoding="utf-8")
    code_path = ROOT / "dataset" / "forge_coder_mixed_4k_overlap4_excluded.jsonl"
    code_rows = [json.loads(line) for line in code_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    exact_eval_prompts = {case["prompt"] for case in evaluation["cases"]}
    if any(any(case_prompt in json.dumps(row, ensure_ascii=False) for case_prompt in exact_eval_prompts) for row in train):
        raise ValueError("held-out prompt leaked into generated SFT rows")
    mixed_rows = code_rows + train
    random.Random(20261012).shuffle(mixed_rows)
    mixed_path = ROOT / "dataset" / "forge_coder_agent_mix_v2.jsonl"
    with mixed_path.open("w", encoding="utf-8", newline="\n") as f:
        for row in mixed_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    manifest = {
        "dataset": "ForgeMind synthetic Agent tool-call traces v1",
        "source": "hand-authored deterministic templates; no external training corpus",
        "license": "CC0-1.0 (project-authored synthetic examples)",
        "training_rows": len(train), "direct_tool_examples": 600, "multi_turn_trajectories": 100,
        "heldout_cases": len(evaluation["cases"]),
        "heldout_sha256": hashlib.sha256(eval_path.read_bytes()).hexdigest(),
        "training_sha256": digest(data_path), "seed": 20261011,
        "note": "Held-out cases are stored separately and must not be merged into SFT data.",
    }
    manifest["dataset"] = "ForgeMind synthetic Agent tool-call traces v2 (native chat-template tool_calls)"
    manifest["format"] = "assistant.tool_calls with structured function names/arguments; tool responses use role=tool"
    (ROOT / "dataset" / "forge_agent_tools_1000_v2.jsonl.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    mixed_manifest = {
        "dataset": "ForgeMind code SFT plus project-authored Agent tool-call SFT v2",
        "source_code_dataset": str(code_path.relative_to(ROOT)),
        "source_code_sha256": digest(code_path),
        "source_tool_dataset": str(data_path.relative_to(ROOT)),
        "source_tool_sha256": digest(data_path),
        "rows": len(mixed_rows), "code_rows": len(code_rows), "tool_rows": len(train),
        "tool_row_fraction": round(len(train) / len(mixed_rows), 6),
        "training_sha256": digest(mixed_path), "heldout_file": str(eval_path.relative_to(ROOT)),
        "heldout_sha256": manifest["heldout_sha256"],
        "declared_license": "Mixed: project-authored synthetic tool examples are CC0-1.0; code rows retain upstream dataset license and attribution obligations.",
        "license_note": "Tool examples are project-authored CC0; code rows inherit mixed-source license/attribution review obligations.",
        "seed": 20261012, "heldout_separation": "Separate JSON file; not included in mixed SFT.",
    }
    (ROOT / "dataset" / "forge_coder_agent_mix_v2.jsonl.manifest.json").write_text(json.dumps(mixed_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"train_rows": len(train), "eval_cases": len(evaluation["cases"]), "mixed_rows": len(mixed_rows), "tool_fraction": mixed_manifest["tool_row_fraction"], "training_sha256": manifest["training_sha256"], "eval_sha256": manifest["heldout_sha256"], "mixed_sha256": mixed_manifest["training_sha256"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
