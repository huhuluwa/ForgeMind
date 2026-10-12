"""Build a deterministic, overlap-filtered Magicoder + CC0 tool-trace SFT mix."""
import argparse
import hashlib
import json
import random
import re
from pathlib import Path


OVERLAP_PATTERNS = [
    r"\brotate_left\b", r"\brotation\b", r"\brotate an? array\b", r"\bleft[- ]rotate\b",
    r"\bcyclic shift\b", r"\bis_palindrome\b", r"\bpalindrome\b", r"\bflatten_once\b",
    r"\bflatten (?:one|a single) level\b", r"\bmatrix transpose\b", r"\btranspose (?:a|the) matrix\b",
    r"\bcsv\b", r"\bquoted comma\b", r"\bnormalize_whitespace\b", r"\bfirst_present\b",
    r"\bdedupe_preserving_order\b",
]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_rows(path):
    rows = []
    with Path(path).open(encoding="utf-8") as source:
        for line_no, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                messages = json.loads(line)["conversations"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ValueError(f"Invalid conversations JSONL: {path}:{line_no}") from exc
            if len(messages) < 2 or messages[-1].get("role") != "assistant":
                continue
            text = "\n".join(str(message.get("content", "")) for message in messages)
            text += json.dumps(messages, ensure_ascii=False)
            rows.append((messages, text))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--magicoder", required=True)
    parser.add_argument("--magicoder-manifest", required=True)
    parser.add_argument("--agent-traces", required=True)
    parser.add_argument("--agent-manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--magicoder-rows", type=int, default=3000)
    parser.add_argument("--agent-rows", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261009)
    args = parser.parse_args()
    if min(args.magicoder_rows, args.agent_rows) < 1:
        parser.error("Both source row counts must be positive")

    magicoder_manifest = json.loads(Path(args.magicoder_manifest).read_text(encoding="utf-8"))
    agent_manifest = json.loads(Path(args.agent_manifest).read_text(encoding="utf-8"))
    if magicoder_manifest.get("dataset") != "ise-uiuc/Magicoder-OSS-Instruct-75K":
        parser.error("Magicoder manifest does not identify the expected upstream dataset")
    if magicoder_manifest.get("declared_license", "").split(" ")[0].lower() != "mit":
        parser.error("Magicoder dataset card no longer declares MIT; re-review before training")
    if not agent_manifest.get("license", "").startswith("CC0-1.0"):
        parser.error("Agent trace source is not recorded as CC0-1.0")
    if magicoder_manifest.get("output_sha256") != sha256(args.magicoder):
        parser.error("Magicoder input hash does not match its manifest")
    if agent_manifest.get("training_sha256") != sha256(args.agent_traces):
        parser.error("Agent trace input hash does not match its manifest")

    patterns = [re.compile(pattern, re.IGNORECASE) for pattern in OVERLAP_PATTERNS]
    magicoder_candidates = load_rows(args.magicoder)
    clean_magicoder, excluded = [], 0
    for row in magicoder_candidates:
        if any(pattern.search(row[1]) for pattern in patterns):
            excluded += 1
        else:
            clean_magicoder.append(row)
    agent_candidates = load_rows(args.agent_traces)
    if len(clean_magicoder) < args.magicoder_rows or len(agent_candidates) < args.agent_rows:
        raise ValueError(
            f"Insufficient clean rows: magicoder={len(clean_magicoder)}, agent={len(agent_candidates)}"
        )

    rng = random.Random(args.seed)
    selected_magicoder = rng.sample(clean_magicoder, args.magicoder_rows)
    selected_agent = rng.sample(agent_candidates, args.agent_rows)
    combined = selected_magicoder + selected_agent
    rng.shuffle(combined)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"conversations": messages} for messages, _ in combined]
    if len(rows) != args.magicoder_rows + args.agent_rows:
        raise ValueError("Source row selection did not preserve requested mixture size")

    with output.open("w", encoding="utf-8", newline="\n") as target:
        for row in rows:
            target.write(json.dumps(row, ensure_ascii=False) + "\n")
    report = {
        "dataset": [
            {"id": magicoder_manifest["dataset"], "revision": magicoder_manifest["dataset_revision"],
             "rows": len(selected_magicoder), "license": "MIT per dataset card; source attribution review remains required",
             "input_sha256": sha256(args.magicoder)},
            {"id": "project-authored-forgemind-agent-tools-v2", "rows": len(selected_agent),
             "license": "CC0-1.0", "input_sha256": sha256(args.agent_traces),
             "source_manifest_sha256": sha256(args.agent_manifest)},
        ],
        "overlap_exclusion": {"patterns": OVERLAP_PATTERNS, "excluded_magicoder_rows": excluded,
                              "scope": "Known fixed code-task names and distinctive task concepts; not a full semantic decontamination guarantee."},
        "candidate_counts": {"magicoder_before_filter": len(magicoder_candidates),
                             "magicoder_after_filter": len(clean_magicoder), "agent_traces": len(agent_candidates)},
        "selected_rows": len(rows), "seed": args.seed,
        "duplicate_full_conversations": len(rows) - len({json.dumps(row["conversations"], ensure_ascii=False, sort_keys=True) for row in rows}),
        "output_sha256": sha256(output),
    }
    manifest = output.with_suffix(output.suffix + ".manifest.json")
    manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
