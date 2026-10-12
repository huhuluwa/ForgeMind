"""Create a reproducible replay mixture of Magicoder and CodeSearchNet SFT rows."""

import argparse
import hashlib
import json
import random
import re
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_rows(path: Path):
    rows = []
    with path.open(encoding="utf-8") as source:
        for line_no, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                messages = json.loads(line)["conversations"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ValueError(f"Invalid conversations JSONL: {path}:{line_no}") from exc
            if len(messages) < 2 or messages[-1].get("role") != "assistant":
                continue
            user_text = "\n".join(str(item.get("content", "")) for item in messages if item.get("role") == "user")
            key = re.sub(r"\s+", " ", user_text).casefold().strip()
            rows.append((key, {"conversations": messages}))
    if not rows:
        raise ValueError(f"No valid conversation rows in {path}")
    return rows


def choose(rows, count, rng, seen):
    available = [(key, row) for key, row in rows if key and key not in seen]
    selected = rng.sample(available, min(count, len(available)))
    seen.update(key for key, _ in selected)
    return [row for _, row in selected]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codesearchnet", required=True)
    parser.add_argument("--magicoder", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--codesearchnet-rows", type=int, default=2000)
    parser.add_argument("--magicoder-rows", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20261010)
    parser.add_argument("--manifest", default="")
    args = parser.parse_args()
    if min(args.codesearchnet_rows, args.magicoder_rows) < 1:
        parser.error("Both source row counts must be positive")

    csn = Path(args.codesearchnet).resolve()
    magicoder = Path(args.magicoder).resolve()
    output = Path(args.output).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else Path(str(output) + ".manifest.json")
    csn_rows, magicoder_rows = read_rows(csn), read_rows(magicoder)
    rng = random.Random(args.seed)
    seen = set()
    selected_csn = choose(csn_rows, args.codesearchnet_rows, rng, seen)
    selected_magicoder = choose(magicoder_rows, args.magicoder_rows, rng, seen)
    rows = selected_csn + selected_magicoder
    rng.shuffle(rows)
    if len(rows) != args.codesearchnet_rows + args.magicoder_rows:
        raise ValueError(f"Deduplication left {len(rows)} rows; requested {args.codesearchnet_rows + args.magicoder_rows}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as target:
        for row in rows:
            target.write(json.dumps(row, ensure_ascii=False) + "\n")
    manifest = {
        "dataset": [
            {"id": "Nan-Do/instructional_code-search-net-python", "revision": "98ba5e1cd9f9603eb9860e9409deaffd34829530", "rows": len(selected_csn), "sha256": sha256(csn), "declared_license": "Apache-2.0 per dataset card; underlying source licenses may vary"},
            {"id": "ise-uiuc/Magicoder-OSS-Instruct-75K", "revision": "5f839b1f368a76b161028bb9edff055db34022b2", "rows": len(selected_magicoder), "sha256": sha256(magicoder), "declared_license": "MIT per dataset card; review underlying source attribution"},
        ],
        "mixture": "50% code-generation filtered CodeSearchNet sample and 50% multi-language Magicoder replay sample",
        "selected_rows": len(rows),
        "source_candidate_rows": {"codesearchnet": len(csn_rows), "magicoder": len(magicoder_rows)},
        "deduplication": "normalized user prompt; applied across both selected sources",
        "seed": args.seed,
        "output_sha256": sha256(output),
        "validation_note": "The trainer creates a deterministic random validation split from this mixture; it is not an official dataset split.",
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
