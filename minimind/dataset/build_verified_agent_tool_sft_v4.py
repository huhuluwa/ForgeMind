"""Add real local test observations to the v3 synthetic tool episodes.

The only executed code is a freshly generated, one-file unittest fixture that
imports pathlib and unittest from the standard library. It runs from a fresh
temporary workspace under D:\\, using the active D-drive Python interpreter.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))
from agent_runtime.code_tools import read_file, replace_text

SOURCE = ROOT / "dataset" / "forge_agent_tools_v3_no_mock_20261010.jsonl"
SOURCE_MANIFEST = SOURCE.with_suffix(SOURCE.suffix + ".manifest.json")
OUTPUT = ROOT / "dataset" / "forge_agent_tools_v4_verified_tests_20261010.jsonl"
MANIFEST = OUTPUT.with_suffix(OUTPUT.suffix + ".manifest.json")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_args(call, expected_name):
    calls = call.get("tool_calls", [])
    if len(calls) != 1:
        raise ValueError(f"expected one {expected_name} call")
    function = calls[0].get("function", {})
    if function.get("name") != expected_name:
        raise ValueError(f"expected {expected_name}, got {function.get('name')}")
    args = function.get("arguments")
    if isinstance(args, str):
        args = json.loads(args)
    if not isinstance(args, dict):
        raise ValueError(f"invalid {expected_name} arguments")
    return args


def make_test(path, expected):
    return (
        "from pathlib import Path\n"
        "import unittest\n"
        "class TestConfiguredValue(unittest.TestCase):\n"
        f"    def test_value(self): self.assertEqual(Path({path!r}).read_text(encoding='utf-8').strip(), {expected!r})\n"
        "if __name__ == '__main__': unittest.main()\n"
    )


def execute_fixture_test(fixture, test_path):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    result = subprocess.run(
        [sys.executable, test_path], cwd=fixture, env=env,
        capture_output=True, text=True, timeout=30, check=False,
    )
    output = result.stdout + result.stderr
    passed = (result.returncode == 0 and "Ran 1 test" in output and
              re.search(r"(?m)^OK\s*$", output) is not None)
    return {
        "passed": passed,
        "exit_code": result.returncode,
        "stdout": result.stdout[-8000:],
        "stderr": result.stderr[-4000:],
    }


def build():
    source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    if digest(SOURCE) != source_manifest.get("data_sha256"):
        raise RuntimeError("v3 dataset hash does not match its manifest")

    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    episode_rows = []
    seen_tests = set()
    for row in rows:
        conv = row.get("conversations", [])
        if not conv or conv[-1].get("role") != "assistant":
            continue
        calls = conv[-1].get("tool_calls", [])
        if not calls or calls[0].get("function", {}).get("name") != "run_tests":
            continue
        if len(conv) == 3:
            continue  # Retained direct-call rows are not fixture episodes.
        if len(conv) != 7 or [m.get("role") for m in conv] != [
            "system", "user", "assistant", "tool", "assistant", "tool", "assistant"
        ]:
            raise RuntimeError("unexpected v3 test episode structure")

        read_args = parse_args(conv[2], "read_file")
        edit_args = parse_args(conv[4], "replace_text")
        test_args = parse_args(conv[6], "run_tests")
        target_path = Path(read_args["path"])
        test_path = Path(test_args["test_path"])
        for candidate in (target_path, test_path):
            if candidate.is_absolute() or ".." in candidate.parts:
                raise RuntimeError("fixture path escaped temporary workspace")
        key = test_path.as_posix()
        if key in seen_tests:
            raise RuntimeError(f"duplicate fixture test path: {key}")
        seen_tests.add(key)

        with tempfile.TemporaryDirectory(prefix="verified_agent_tool_fixture_v4_", dir=ROOT / "tmp") as temp:
            fixture = Path(temp)
            target = fixture / target_path
            target.parent.mkdir(parents=True, exist_ok=True)
            original = json.loads(conv[3]["content"])
            old_content = original.get("content")
            if not isinstance(old_content, str) or not old_content.endswith("\n"):
                raise RuntimeError("unexpected observed read_file result")
            target.write_text(old_content, encoding="utf-8")

            os.environ["ENABLE_CODE_WRITE"] = "1"
            read_result = read_file(str(fixture), target_path.as_posix())
            if read_result != original:
                raise RuntimeError("fresh read_file observation differs from v3 trace")
            edit_result = replace_text(str(fixture), **edit_args)
            expected_text = edit_args.get("new_text")
            if (not edit_result.get("applied") or
                    target.read_text(encoding="utf-8") != expected_text + "\n"):
                raise RuntimeError("fresh replace_text observation failed")

            test_file = fixture / test_path
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text(make_test(target_path.as_posix(), expected_text), encoding="utf-8")
            test_result = execute_fixture_test(fixture, test_path.as_posix())
            if test_result["passed"] is not True:
                raise RuntimeError(f"actual fixture test failed for {key}: {test_result}")

        conv.extend([
            {"role": "tool", "content": json.dumps(test_result, ensure_ascii=False)},
            {"role": "assistant", "content":
             f"已完成修改；工具真实返回显示 `{key}` 中的 1 项测试通过。"},
        ])
        episode_rows.append({"test_path": key, "passed": True, "exit_code": test_result["exit_code"]})

    if len(episode_rows) != source_manifest.get("observed_fixture_episodes"):
        raise RuntimeError(f"expected {source_manifest.get('observed_fixture_episodes')} verified tests, got {len(episode_rows)}")

    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    data = payload.encode("utf-8")
    manifest = {
        "dataset": "ForgeMind Agent SFT v4, v3 observed edits plus executed local fixture tests",
        "source_dataset": SOURCE.name,
        "source_sha256": digest(SOURCE),
        "license": source_manifest.get("license"),
        "rows": len(rows),
        "verified_test_episodes": len(episode_rows),
        "test_runner": "active D-drive Python interpreter running a freshly generated standard-library unittest fixture",
        "test_execution": "each test ran in a fresh temporary directory under project/tmp; no third-party project code executed",
        "all_test_runs_passed": all(item["passed"] for item in episode_rows),
        "episodes": episode_rows,
        "limitations": [
            "project-authored synthetic one-file edits; this does not establish general coding-agent quality",
            "the test asserts the requested literal value, not broad integration behavior",
            "candidate remains untrained; create a task-group split and run leakage audits before training",
        ],
        "data_sha256": hashlib.sha256(data).hexdigest(),
    }
    OUTPUT.write_bytes(data)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "rows": len(rows),
                      "verified_tests": len(episode_rows), "all_passed": manifest["all_test_runs_passed"],
                      "sha256": manifest["data_sha256"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build()
