"""Build a small plain-text code corpus from the locally prepared SFT JSONL."""

import argparse
import json
from pathlib import Path


def extract_assistant_text(source: Path, destination: Path) -> int:
    count = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open(encoding="utf-8") as src, destination.open("w", encoding="utf-8", newline="\n") as dst:
        for line_no, line in enumerate(src, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            messages = row.get("conversations", [])
            text = "\n\n".join(
                str(message.get("content", "")).strip()
                for message in messages
                if message.get("role") == "assistant" and str(message.get("content", "")).strip()
            )
            if not text:
                raise ValueError(f"row {line_no} has no assistant content")
            dst.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="dataset/forge_magicoder_sft.jsonl")
    parser.add_argument("--output", default="output/data/forgemind64_pretrain.jsonl")
    args = parser.parse_args()
    rows = extract_assistant_text(Path(args.input), Path(args.output))
    print(json.dumps({"rows": rows, "output": args.output}, ensure_ascii=False))


if __name__ == "__main__":
    main()
