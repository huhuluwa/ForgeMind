"""Build a small local patch-SFT set from pinned, permissively licensed SWE-bench repos."""

import argparse
import hashlib
import json
import os
import random
import re
import tempfile
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DATASET_ID = "princeton-nlp/SWE-bench"
LICENSED_REPOS = {
    "DataDog/integrations-core": "BSD-3-Clause",
    "JohnSnowLabs/spark-nlp": "Apache-2.0",
    "Lightning-AI/lightning": "Apache-2.0",
    "PrefectHQ/prefect": "Apache-2.0",
}
SYSTEM_PROMPT = (
    "You are a careful software engineering assistant. Given a repository issue, produce a "
    "minimal unified diff that addresses it. Do not claim tests were run unless they were."
)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip().casefold()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True, help="Pinned 40-character Hub commit SHA")
    parser.add_argument("--output", required=True, help="Local SFT JSONL output, preferably on D:")
    parser.add_argument("--max-rows", type=int, default=600, help="0 includes all eligible rows")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cache-dir", default="", help="Optional datasets cache directory")
    parser.add_argument("--max-chars", type=int, default=32000)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", args.revision):
        parser.error("--revision must be a 40-character commit SHA")
    if args.max_rows < 0 or args.max_chars < 1:
        parser.error("--max-rows must be >= 0 and --max-chars must be > 0")

    output = Path(args.output).resolve()
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    if not args.force and (output.exists() or manifest_path.exists()):
        parser.error("Output exists; choose another path or pass --force")
    try:
        from datasets import load_dataset
    except ImportError as exc:
        parser.error(f"Install the repository requirements first ({exc.name} is missing)")

    dataset = load_dataset(
        DATASET_ID,
        split="train",
        revision=args.revision,
        cache_dir=args.cache_dir or None,
    )
    candidates = []
    seen = set()
    skipped = Counter()
    for row in dataset:
        repo = row.get("repo") or ""
        issue = (row.get("problem_statement") or "").strip()
        patch = (row.get("patch") or "").strip()
        if repo not in LICENSED_REPOS:
            skipped["repo_not_in_verified_allowlist"] += 1
            continue
        if not issue or not patch:
            skipped["missing_issue_or_patch"] += 1
            continue
        if max(len(issue), len(patch)) > args.max_chars:
            skipped["oversize"] += 1
            continue
        key = hashlib.sha256((normalize(repo) + "\0" + normalize(issue) + "\0" + normalize(patch)).encode("utf-8")).hexdigest()
        if key in seen:
            skipped["duplicate"] += 1
            continue
        seen.add(key)
        prompt = (
            f"Repository: {repo}\n"
            f"Issue ({row.get('instance_id', '')}):\n{issue}\n\n"
            "Return only a unified diff. The repository checkout is not included in this prompt."
        )
        candidates.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": patch},
            ]
        })
    random.Random(args.seed).shuffle(candidates)
    if args.max_rows:
        candidates = candidates[:args.max_rows]
    if not candidates:
        raise RuntimeError("No examples passed the repository and content filters")

    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as target:
            for sample in candidates:
                target.write(json.dumps(sample, ensure_ascii=False) + "\n")
            target.flush()
            os.fsync(target.fileno())
        os.replace(temp_name, output)
    except Exception:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
        raise

    by_repo = Counter(
        item["conversations"][1]["content"].splitlines()[0].removeprefix("Repository: ")
        for item in candidates
    )
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": DATASET_ID,
        "dataset_revision": args.revision,
        "split": "train",
        "dataset_card_license": "No dataset-level license field was declared on the pinned card; source repos below were individually checked via the GitHub license API.",
        "source_repositories": LICENSED_REPOS,
        "source_license_evidence": "https://api.github.com/repos/{owner}/{repo}/license (checked 2026-10-09); retain source notices.",
        "selection_note": "Only a local research adapter dataset. Not bundled for redistribution. Inputs contain issue text and target patches, but no repository checkout context; validate gains on held-out repository tasks.",
        "seed": args.seed,
        "max_rows": args.max_rows,
        "max_chars": args.max_chars,
        "accepted_rows": len(candidates),
        "rows_by_repository": dict(sorted(by_repo.items())),
        "skipped": dict(sorted(skipped.items())),
        "output_file": output.name,
        "output_sha256": sha256_file(output),
    }
    manifest_tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    manifest_tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(manifest_tmp, manifest_path)
    print(json.dumps({"accepted_rows": len(candidates), "rows_by_repository": dict(sorted(by_repo.items())),
                      "output": str(output), "manifest": str(manifest_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
