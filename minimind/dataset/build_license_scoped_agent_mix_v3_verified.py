"""Build a clean successor mix, replacing mocked agent receipts with verified fixture traces."""
import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dataset"
SOURCES = [
    ("forge_magicoder_python_3k_20261009.jsonl", "MIT-declared Magicoder dataset; retain attribution and upstream notices"),
    ("forge_agent_tools_v4_verified_tests_20261010.jsonl", "Project-authored CC0-1.0; 100 local generated tests actually executed"),
    ("forge_agentic_magicoder_replace_v1_20261010.jsonl", "Derived from MIT-declared Magicoder sample; retain attribution and upstream notices"),
]
OUTPUT = DATA / "forge_coder_license_scoped_agent_mix_v3_verified_20261010.jsonl"
MANIFEST = OUTPUT.with_suffix(OUTPUT.suffix + ".manifest.json")
SEED = 20261011


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_verified(filename):
    path = DATA / filename
    manifest_path = path.with_suffix(path.suffix + ".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = next((manifest[k] for k in ("sha256", "output_sha256", "data_sha256") if manifest.get(k)), None)
    if not expected or sha256(path) != expected:
        raise RuntimeError(f"source hash mismatch: {filename}")
    if manifest.get("active_holdout_used") is True:
        raise RuntimeError(f"source includes active holdout: {filename}")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(not isinstance(row.get("conversations"), list) for row in rows):
        raise RuntimeError(f"invalid conversation row in {filename}")
    return path, manifest, rows


def main():
    source_records = []
    all_rows = []
    for filename, license_note in SOURCES:
        path, manifest, rows = read_verified(filename)
        source_records.append({"path": filename, "sha256": sha256(path),
                               "rows": len(rows), "license_note": license_note})
        all_rows.extend(rows)

    v4 = json.loads((DATA / "forge_agent_tools_v4_verified_tests_20261010.jsonl.manifest.json").read_text(encoding="utf-8"))
    if v4.get("verified_test_episodes") != 100 or v4.get("all_test_runs_passed") is not True:
        raise RuntimeError("v4 actual test evidence gate failed")
    if not v4.get("fit_audit", {}).get("status", "").startswith("passed"):
        raise RuntimeError("v4 trainer fit preflight is missing")
    if len(all_rows) != 4600 or [r["rows"] for r in source_records] != [3000, 1000, 600]:
        raise RuntimeError(f"unexpected row counts: {[r['rows'] for r in source_records]}")

    random.Random(SEED).shuffle(all_rows)
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in all_rows).encode("utf-8")
    OUTPUT.write_bytes(payload)
    manifest = {
        "dataset": "ForgeMind license-scoped Agent SFT v3, replacing mocked receipts with verified fixture traces",
        "row_count": len(all_rows), "seed": SEED, "sources": source_records,
        "active_holdout_used": False,
        "removed_source": "forge_agent_tools_1000_v2.jsonl; its unexecuted synthetic test receipts are not included",
        "verified_agent_source": "forge_agent_tools_v4_verified_tests_20261010.jsonl",
        "verified_agent_tests": 100, "all_verified_agent_tests_passed": True,
        "trainer_fit_audit": v4["fit_audit"],
        "split_policy": "The trainer groups identical user prompts; additionally freeze an independent semantic/repository holdout before training.",
        "license_and_redistribution": "Local research mix. Magicoder-derived examples are retained with attribution; review upstream code notices before redistributing derived weights.",
        "limitations": ["100 project-authored test fixtures are simple literal-value edits, not broad repository repairs",
                        "the Magicoder patch-format source rows do not carry executed repository test outcomes",
                        "candidate has not been trained or evaluated"],
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "rows": len(all_rows), "source_rows": [r["rows"] for r in source_records],
                      "verified_tests": 100, "sha256": manifest["sha256"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()