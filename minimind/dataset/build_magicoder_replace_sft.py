"""Create license-scoped code-agent demonstrations from the local Magicoder sample."""

import ast
import hashlib
import json
import random
import re
from pathlib import Path

from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dataset" / "forge_magicoder_python_3k_20261009.jsonl"
MODEL = ROOT.parent / "shared" / "models" / "Qwen2.5-Coder-7B-Instruct-Safetensors"
OUTPUT = ROOT / "dataset" / "forge_agentic_magicoder_replace_v1_20261010.jsonl"
MANIFEST = OUTPUT.with_suffix(OUTPUT.suffix + ".manifest.json")
SEED = 20261010
LIMIT = 600
MAX_LENGTH = 512
MARKER = "# TODO: implement solution"
SYSTEM = (
    "你是代码开发 Agent。当前工具只有 replace_text，调用格式为 "
    "<tool_call>{\"name\":\"replace_text\",\"arguments\":{\"path\":\"solution.py\","
    "\"old_text\":\"# TODO: implement solution\",\"new_text\":\"完整代码\"}}</tool_call>。"
    "已经读取 solution.py，文件内容只有一行 `# TODO: implement solution`。"
    "请依据用户任务替换这行；new_text 必须是完整可运行 Python 代码，不声称已运行测试。"
)


def extract_code(answer):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", answer, re.S | re.I)
    for candidate in reversed(blocks):
        candidate = candidate.strip()
        try:
            tree = ast.parse(candidate)
        except SyntaxError:
            continue
        if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for node in tree.body):
            return candidate
    return None


def make_row(user_text, code):
    return {"conversations": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": "replace_text",
            "arguments": {"path": "solution.py", "old_text": MARKER, "new_text": code},
        }}]},
    ]}


def main():
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL), local_files_only=True)
    candidates, seen = [], set()
    with SOURCE.open(encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            messages = row.get("conversations", [])
            user = next((message.get("content", "") for message in messages if message.get("role") == "user"), "")
            answer = next((message.get("content", "") for message in reversed(messages)
                           if message.get("role") == "assistant" and message.get("content")), "")
            code = extract_code(answer)
            if not user or not code or user in seen:
                continue
            seen.add(user)
            item = make_row(user, code)
            tokens = tokenizer.apply_chat_template(item["conversations"], tokenize=True, add_generation_prompt=False)
            if len(tokens) <= MAX_LENGTH:
                candidates.append(item)

    rng = random.Random(SEED)
    rng.shuffle(candidates)
    rows = candidates[:LIMIT]
    if len(rows) < 200:
        raise RuntimeError(f"Only {len(rows)} valid, length-safe demonstrations; require at least 200.")
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as target:
        for row in rows:
            target.write(json.dumps(row, ensure_ascii=False) + "\n")
    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    manifest = {
        "dataset": "ForgeMind project-authored code-agent formatting conversion v1",
        "source_dataset": "ise-uiuc/Magicoder-OSS-Instruct-75K local 3000-row sample",
        "source_manifest": "forge_magicoder_python_3k_20261009.jsonl.manifest.json",
        "license_note": "Derived from a local sample whose dataset card declares MIT; retain attribution and review upstream code notices before redistribution.",
        "generation": "Each row preserves the exact source user prompt as its task-group key and supervises one replace_text tool call with the parsed Python answer.",
        "training_use": True,
        "active_holdout_used": False,
        "seed": SEED,
        "source_rows": 3000,
        "valid_code_rows_under_max_length": len(candidates),
        "output_rows": len(rows),
        "max_length": MAX_LENGTH,
        "sha256": digest,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
