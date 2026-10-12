"""Build a reproducible Magicoder + project-authored CC0 tool-trace SFT candidate."""
import argparse
import hashlib
import json
import os
import random
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dataset"
SOURCES = (
    (DATA / "forge_magicoder_python_3k_20261009.jsonl", "ise-uiuc/Magicoder-OSS-Instruct-75K", "output_sha256"),
    (DATA / "forge_agent_tools_1000_v2.jsonl", "CC0-1.0 (project-authored synthetic examples)", "training_sha256"),
)
DEFAULT_OUTPUT = DATA / "forge_coder_license_scoped_sft_v1_20261010.jsonl"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_source(path, expected, hash_field):
    manifest_path = Path(f"{path}.manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    identity = manifest.get("dataset") if hash_field == "output_sha256" else manifest.get("license")
    if identity != expected or manifest.get(hash_field) != sha256(path):
        raise ValueError(f"Source identity or hash mismatch: {path}")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != manifest.get("accepted_rows", manifest.get("training_rows")):
        raise ValueError(f"Source row count mismatch: {path}")
    if any(not isinstance(row, dict) or not isinstance(row.get("conversations"), list) for row in rows):
        raise ValueError(f"Unexpected chat schema: {path}")
    return rows, manifest_path, manifest


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=20261010)
    args = parser.parse_args()
    output = args.output.resolve()
    if output in {path.resolve() for path, _, _ in SOURCES}:
        parser.error("output must differ from each source file")

    code, code_manifest_path, code_manifest = load_source(*SOURCES[0])
    tools, tools_manifest_path, tools_manifest = load_source(*SOURCES[1])
    rows = code + tools
    random.Random(args.seed).shuffle(rows)
    serialized = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    atomic_write(output, serialized)
    manifest = {
        "dataset": "ForgeMind license-scoped code and CC0 tool SFT candidate v1",
        "seed": args.seed,
        "row_counts": {"Magicoder_MIT_declared": len(code), "project_authored_CC0": len(tools)},
        "total_rows": len(rows),
        "sources": [
            {"path": code_manifest_path.name, "dataset": code_manifest["dataset"],
             "revision": code_manifest.get("dataset_revision"), "license": code_manifest["declared_license"],
             "sha256": sha256(SOURCES[0][0])},
            {"path": tools_manifest_path.name, "dataset": tools_manifest.get("dataset"),
             "license": tools_manifest["license"], "sha256": sha256(SOURCES[1][0])},
        ],
        "excluded_source": "SWE-bench-derived repo traces; synthetic read/search fixtures have no executed patch/test outcomes and carry source-specific repository licenses.",
        "declared_license": "Mixed-source training candidate: Magicoder dataset card declares MIT; project-authored tool traces are CC0-1.0. Review Magicoder attribution and upstream notices before redistributing derived weights.",
        "use_limit": "Training candidate for local research. Magicoder's dataset card declares MIT but asks users to retain attribution and review source-code notices before redistribution; this manifest does not grant additional rights.",
        "output_sha256": None,
    }
    manifest["output_sha256"] = sha256(output)
    manifest_path = Path(f"{output}.manifest.json")
    atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(output), "manifest": str(manifest_path),
                      "rows": manifest["row_counts"], "total": len(rows),
                      "sha256": manifest["output_sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
