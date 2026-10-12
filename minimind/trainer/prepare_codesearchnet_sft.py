"""Prepare a small, deterministic code-generation SFT sample from CodeSearchNet instructions."""

import argparse
import hashlib
import json
import random
import re
from pathlib import Path

from datasets import load_dataset


GENERATION = re.compile(
    r"\b(?:implement|write|create|build|develop|construct|define)\b.{0,100}\b(?:function|method|class|program|code|script|api)\b",
    re.IGNORECASE | re.DOTALL,
)
EXPLANATION = re.compile(r"\b(?:explain|describe|summar(?:y|ize)|documentation|docstring)\b", re.IGNORECASE)
CODE = re.compile(r"```|^\s*(?:def|class|async\s+def|import\s|from\s)\w?", re.IGNORECASE | re.MULTILINE)
SYSTEM = (
    "You are ForgeMind, a careful coding assistant. Follow the requested behavior, "
    "consider edge cases, and return a correct implementation."
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def select_rows(dataset, count: int, seed: int):
    candidates = []
    seen = set()
    for row in dataset:
        instruction = str(row.get("INSTRUCTION", "")).strip()
        response = str(row.get("RESPONSE", "")).strip()
        if not instruction or not response or len(instruction) > 12_000 or len(response) > 12_000:
            continue
        if not GENERATION.search(instruction) or EXPLANATION.search(instruction) or not CODE.search(response):
            continue
        key = re.sub(r"\s+", " ", instruction).casefold()
        if key in seen:
            continue
        seen.add(key)
        candidates.append((instruction, response))
    if len(candidates) < count:
        raise ValueError(f"Requested {count} examples but only found {len(candidates)} after filtering")
    return random.Random(seed).sample(candidates, count), len(candidates)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Downloaded CodeSearchNet Parquet file")
    parser.add_argument("--output", required=True, help="Output SFT JSONL")
    parser.add_argument("--rows", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=20261009)
    parser.add_argument("--manifest", default="", help="Manifest path; defaults to <output>.manifest.json")
    args = parser.parse_args()
    if args.rows < 2:
        parser.error("--rows must be at least 2")

    source = Path(args.input).resolve()
    output = Path(args.output).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else Path(str(output) + ".manifest.json")
    dataset = load_dataset("parquet", data_files=str(source), split="train")
    selected, filtered_count = select_rows(dataset, args.rows, args.seed)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as target:
        for instruction, response in selected:
            row = {"conversations": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": instruction},
                {"role": "assistant", "content": response},
            ]}
            target.write(json.dumps(row, ensure_ascii=False) + "\n")
    manifest = {
        "dataset": "Nan-Do/instructional_code-search-net-python",
        "dataset_revision": "98ba5e1cd9f9603eb9860e9409deaffd34829530",
        "declared_license": "Apache-2.0 per Hugging Face dataset card; review underlying CodeSearchNet source licenses before redistribution or commercial use",
        "source_task": "Python instruction-to-code generation examples only",
        "source_parquet_sha256": sha256(source),
        "source_rows": len(dataset),
        "filtered_unique_generation_rows": filtered_count,
        "selected_rows": len(selected),
        "seed": args.seed,
        "filter": "implementation-oriented prompt, code-shaped answer, excludes explanation/documentation prompts, deduplicated by normalized prompt",
        "output_sha256": sha256(output),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
