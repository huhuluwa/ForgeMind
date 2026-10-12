"""Prepare a small, traceable SFT subset from the official Magicoder dataset."""

import argparse
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


DATASET_ID = "ise-uiuc/Magicoder-OSS-Instruct-75K"
DATASET_CARD = "https://huggingface.co/datasets/ise-uiuc/Magicoder-OSS-Instruct-75K"
LICENSE = "MIT (dataset-card declaration; review upstream code attribution separately)"
SYSTEM_PROMPT = (
    "You are a careful software engineering assistant. Explain assumptions and edge cases, "
    "write correct code, and never claim that code was executed unless it was tested."
)


def normalize(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().casefold()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Output SFT JSONL path")
    parser.add_argument("--max-rows", type=int, default=3000, help="Small-scale cap; 0 means no cap")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--revision", default="", help="Optional exact Hugging Face commit SHA for reproduction")
    parser.add_argument("--lang", default="", help="Optional exact language filter, e.g. python")
    parser.add_argument("--max-chars", type=int, default=24000, help="Skip unusually long prompt/answer pairs")
    parser.add_argument("--force", action="store_true", help="Replace an existing output and manifest")
    args = parser.parse_args()
    if args.max_rows < 0 or args.max_chars < 1:
        parser.error("--max-rows must be >= 0 and --max-chars must be > 0")

    output = Path(args.output).resolve()
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    if not args.force and (output.exists() or manifest_path.exists()):
        parser.error("Output exists; choose another path or pass --force")

    try:
        from datasets import load_dataset
        from huggingface_hub import HfApi
    except ImportError as exc:
        parser.error(f"Install the repository requirements first ({exc.name} is missing)")

    # Resolve and pin the Hub revision before streaming so the manifest identifies
    # the exact source snapshot used to build the training file.
    revision = args.revision or HfApi().dataset_info(DATASET_ID).sha
    if not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        parser.error("--revision must be a 40-character commit SHA")
    stream = load_dataset(DATASET_ID, split="train", revision=revision, streaming=True)
    stream = stream.shuffle(seed=args.seed, buffer_size=4096)

    output.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    accepted = skipped = duplicates = 0
    languages = {}
    fd, temp_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as target:
            for row in stream:
                prompt = str(row.get("problem") or "").strip()
                answer = str(row.get("solution") or "").strip()
                lang = str(row.get("lang") or "unknown").strip().lower()
                if args.lang and lang != args.lang.lower():
                    continue
                if not prompt or not answer or max(len(prompt), len(answer)) > args.max_chars:
                    skipped += 1
                    continue
                key = hashlib.sha256((normalize(prompt) + "\0" + normalize(answer)).encode("utf-8")).hexdigest()
                if key in seen:
                    duplicates += 1
                    continue
                seen.add(key)
                sample = {
                    "conversations": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": answer},
                    ]
                }
                target.write(json.dumps(sample, ensure_ascii=False) + "\n")
                accepted += 1
                languages[lang] = languages.get(lang, 0) + 1
                if args.max_rows and accepted >= args.max_rows:
                    break
            target.flush()
            os.fsync(target.fileno())
        if accepted == 0:
            raise RuntimeError("No examples passed the filters; output was not installed")
        os.replace(temp_name, output)
    except Exception:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
        raise

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": DATASET_ID,
        "dataset_revision": revision,
        "dataset_card": DATASET_CARD,
        "declared_license": LICENSE,
        "attribution_note": "Retain dataset and upstream source notices. Review per-source terms before redistribution or commercial use.",
        "seed": args.seed,
        "revision_was_pinned_by_user": bool(args.revision),
        "lang_filter": args.lang or None,
        "max_rows": args.max_rows,
        "max_chars": args.max_chars,
        "accepted_rows": accepted,
        "skipped_invalid_or_oversize": skipped,
        "duplicates_removed": duplicates,
        "rows_by_language": dict(sorted(languages.items())),
        "output_file": output.name,
        "output_sha256": sha256_file(output),
    }
    manifest_tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    manifest_tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(manifest_tmp, manifest_path)
    print(json.dumps({"accepted_rows": accepted, "skipped": skipped, "duplicates": duplicates,
                      "revision": revision, "output": str(output), "manifest": str(manifest_path)},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
