"""Create opt-in SFT examples from a user-authorized Volcengine Ark teacher API."""

import argparse
import json
import os
import time

from openai import OpenAI


DEFAULT_MODEL = "doubao-seed-evolving"
SYSTEM_PROMPT = (
    "你是严谨的中文软件工程助手。先理解需求和仓库上下文，再给出可执行、最小且安全的方案。"
    "代码任务要说明假设、边界与验证方法；不编造运行结果。"
)


def main():
    parser = argparse.ArgumentParser(description="Generate SFT data with a configured Ark teacher model")
    parser.add_argument("--input", required=True, help="JSONL containing prompt and optional system fields")
    parser.add_argument("--output", required=True, help="Output SFT JSONL path")
    parser.add_argument("--model", default=os.environ.get("DOUBAO_TEACHER_MODEL", DEFAULT_MODEL))
    parser.add_argument("--limit", type=int, default=0, help="0 processes all input records")
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between API calls")
    args = parser.parse_args()

    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        parser.error("Set ARK_API_KEY in the process environment; never put credentials in this script.")
    if os.environ.get("FORGEMIND_ARK_SAFE_MODE") != "1":
        parser.error("Free-only mode: confirm Ark Safe Experience Mode and free quota, then set FORGEMIND_ARK_SAFE_MODE=1.")
    client = OpenAI(api_key=api_key, base_url="https://ark.cn-beijing.volces.com/api/v3", max_retries=3, timeout=120)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    seen = set()
    if os.path.exists(args.output):
        with open(args.output, "r", encoding="utf-8") as existing:
            for line in existing:
                try:
                    messages = json.loads(line)["conversations"]
                    user = next(message["content"] for message in messages if message["role"] == "user")
                    system = next((message["content"] for message in messages if message["role"] == "system"), SYSTEM_PROMPT)
                    seen.add((system, user))
                except (json.JSONDecodeError, KeyError, TypeError, StopIteration):
                    continue
    written = 0
    with open(args.input, "r", encoding="utf-8") as source, open(args.output, "a", encoding="utf-8") as target:
        for line_no, line in enumerate(source, 1):
            if args.limit and written >= args.limit:
                break
            try:
                item = json.loads(line)
                prompt = str(item["prompt"]).strip()
                system = str(item.get("system") or SYSTEM_PROMPT).strip()
                if not prompt:
                    continue
                if (system, prompt) in seen:
                    continue
                response = client.chat.completions.create(
                    model=args.model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=4096,
                )
                answer = response.choices[0].message.content
                if not answer or not answer.strip():
                    continue
                row = {"conversations": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": answer.strip()},
                ]}
                target.write(json.dumps(row, ensure_ascii=False) + "\n")
                target.flush()
                seen.add((system, prompt))
                written += 1
                time.sleep(max(0.0, args.sleep))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                print(f"skip line {line_no}: {type(exc).__name__}")
            except Exception as exc:
                print(f"stop at line {line_no}: API request failed ({type(exc).__name__})")
                break
    print(f"wrote {written} examples using {args.model}")


if __name__ == "__main__":
    main()
