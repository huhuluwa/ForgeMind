"""Read-only code navigation and opt-in patch/test tools for a bounded workspace."""

import ast
import os
import subprocess
import tempfile
from pathlib import Path


SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "checkpoints", "out"}
TEXT_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".c", ".h", ".cpp", ".cs", ".json", ".yaml", ".yml", ".toml", ".md", ".sh"}


def _atomic_write_text(target, content):
    """Replace one text file without exposing a partially written version."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=target.parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
        try:
            os.chmod(temporary, target.stat().st_mode)
        except OSError:
            pass
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _workspace(root):
    if not root:
        raise ValueError("Set CODE_WORKSPACE to the repository the agent may inspect.")
    # Path.resolve() may request a Windows final-path handle that managed workspaces deny.
    path = Path(os.path.realpath(os.path.abspath(os.fspath(root))))
    if not path.is_dir():
        raise ValueError("CODE_WORKSPACE must be a directory.")
    return path


def _safe_path(root, relative):
    relative = Path(str(relative))
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        raise ValueError("Path must stay inside CODE_WORKSPACE.")
    candidate = Path(os.path.realpath(os.path.abspath(os.fspath(root / relative))))
    if not candidate.exists():
        matches = []
        for directory, names, files in os.walk(root):
            names[:] = [name for name in names if name not in SKIP_DIRS and not name.startswith(".")]
            if relative.name in files:
                alternative = Path(os.path.realpath(os.path.abspath(os.fspath(Path(directory) / relative.name))))
                if alternative.is_relative_to(root) and alternative.is_file():
                    matches.append(alternative)
                    if len(matches) > 1:
                        break
        if len(matches) != 1:
            reason = "ambiguous" if matches else "missing"
            raise ValueError(f"File path is {reason} inside CODE_WORKSPACE; use a unique repository-relative path.")
        candidate = matches[0]
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise ValueError("Path must identify a file inside CODE_WORKSPACE.")
    if candidate.stat().st_size > 250_000:
        raise ValueError("File is larger than the 250 KB read limit.")
    return candidate


def read_file(root, path):
    root = _workspace(root)
    try:
        target = _safe_path(root, path)
        return {"path": target.relative_to(root).as_posix(), "content": target.read_text(encoding="utf-8")}
    except (OSError, UnicodeError, ValueError) as exc:
        return {"error": str(exc)}


def search_code(root, query, max_results=30):
    root = _workspace(root)
    query = str(query).strip()
    if not query or len(query) > 200:
        return {"error": "query must contain 1-200 characters"}
    found, visited = [], 0
    needle = query.casefold()
    for directory, names, files in os.walk(root):
        names[:] = [name for name in names if name not in SKIP_DIRS and not name.startswith(".")]
        for name in files:
            target = Path(directory) / name
            if target.suffix.lower() not in TEXT_SUFFIXES:
                continue
            visited += 1
            if visited > 2500:
                return {"query": query, "matches": found, "truncated": True}
            try:
                lines = target.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError):
                continue
            for line_no, line in enumerate(lines, 1):
                if needle in line.casefold():
                    found.append({"path": target.relative_to(root).as_posix(), "line": line_no, "text": line[:500]})
                    if len(found) >= min(max(int(max_results), 1), 50):
                        return {"query": query, "matches": found, "truncated": True}
    return {"query": query, "matches": found, "truncated": False}


def _patch_paths(patch):
    paths, seen = [], set()
    for line in patch.splitlines():
        if not (line.startswith("--- ") or line.startswith("+++ ")):
            continue
        marker, name = line[:4], line[4:].split("\t", 1)[0]
        if name == "/dev/null":
            continue
        prefix = "a/" if marker == "--- " else "b/"
        if not name.startswith(prefix):
            raise ValueError("Patch headers must use repository-relative a/ and b/ paths.")
        name = name[len(prefix):]
        path = Path(name)
        if not name or path.is_absolute() or ".." in path.parts:
            raise ValueError("Patch paths must stay inside CODE_WORKSPACE.")
        if marker == "+++ " and name not in seen:
            paths.append(name)
            seen.add(name)
    if not paths or len(paths) > 20:
        raise ValueError("Patch must update between 1 and 20 workspace files.")
    return paths


def _normalize_model_patch(patch):
    """Repair common model diff formatting errors without changing operations."""
    candidate = patch
    stripped = candidate.strip()
    if (len(stripped) >= 2 and stripped[0] == stripped[-1] == '"'
            and stripped[1:].lstrip().startswith(("diff --git ", "--- "))):
        candidate = stripped[1:-1]
    raw_lines = candidate.splitlines()
    repaired_lines = []
    i = 0
    while i < len(raw_lines):
        old = raw_lines[i]
        new = raw_lines[i + 1] if i + 1 < len(raw_lines) else ""
        if old.startswith("+--- ") and new.startswith("+++ "):
            old_path = old[5:].split("\t", 1)[0]
            new_path = new[4:].split("\t", 1)[0]
            old_rel = old_path[2:] if old_path.startswith("a/") else old_path
            new_rel = new_path[2:] if new_path.startswith("b/") else new_path
            if (old_rel == new_rel and old_rel and not Path(old_rel).is_absolute()
                    and ".." not in Path(old_rel).parts):
                repaired_lines.extend((f"--- {old_path}", f"+++ {new_path}"))
                i += 2
                continue
        repaired_lines.append(old)
        i += 1
    candidate = "\n".join(repaired_lines)
    if not candidate.lstrip().startswith("diff --git "):
        raw_lines = candidate.splitlines()
        normalized, i = [], 0
        while i < len(raw_lines):
            old = raw_lines[i]
            new = raw_lines[i + 1] if i + 1 < len(raw_lines) else ""
            if not (old.startswith("--- ") and new.startswith("+++ ")):
                normalized.append(old)
                i += 1
                continue
            old_path = old[4:].split("\t", 1)[0]
            new_path = new[4:].split("\t", 1)[0]
            if old_path == "/dev/null":
                rel = new_path[2:] if new_path.startswith("b/") else new_path
            elif new_path == "/dev/null":
                rel = old_path[2:] if old_path.startswith("a/") else old_path
            elif old_path.startswith("a/") and new_path.startswith("b/") and old_path[2:] == new_path[2:]:
                rel = old_path[2:]
            elif old_path == new_path and not old_path.startswith(("a/", "b/")):
                rel = old_path
            else:
                return candidate
            if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
                return candidate
            normalized.extend((f"diff --git a/{rel} b/{rel}", f"--- a/{rel}" if old_path != "/dev/null" else "--- /dev/null",
                               f"+++ b/{rel}" if new_path != "/dev/null" else "+++ /dev/null"))
            i += 2
        candidate = "\n".join(normalized)
        if not candidate.lstrip().startswith("diff --git "):
            return patch
    for _ in range(4):
        previous = candidate
        candidate = candidate.replace("\\\\", "\\")
        candidate = candidate.replace(r"\r\n", "\n").replace(r"\n", "\n").replace(r"\t", "\t")
        candidate = candidate.replace('\\"', '"').replace("\\'", "'")
        if candidate == previous:
            break
    lines, in_hunk = [], False
    for line in candidate.splitlines():
        if not line:
            continue
        if line.startswith("-diff --git "):
            line = line[1:]
        if line.startswith("index "):
            fields = line.split()
            hashes = fields[1].split("..") if len(fields) > 1 else []
            if (len(hashes) != 2 or not all(hashes)
                    or not all(char in "0123456789abcdef" for value in hashes for char in value)):
                continue
        if line.startswith("diff --git ") or line.startswith(("--- ", "+++ ", "@@ ")):
            in_hunk = line.startswith("@@ ")
        elif in_hunk and (not line or line[0] not in " +-\\"):
            line = " " + line
        lines.append(line)
    return "\n".join(lines) + "\n"


def _preflight_patch(root, patch, paths):
    """Apply a patch to a D-drive workspace copy and parse changed Python files."""
    try:
        with tempfile.TemporaryDirectory(prefix=".forgemind-patch-check-", dir=root) as temp_name:
            temp_root = Path(temp_name)
            subprocess.run(
                ["git", "init", "-q"], cwd=temp_root,
                capture_output=True, timeout=15, check=True,
            )
            for name in paths:
                source = root / name
                if source.is_file():
                    destination = temp_root / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(source.read_bytes())

            check = subprocess.run(
                ["git", "apply", "--recount", "--unidiff-zero", "--check", "-"], cwd=temp_root,
                input=patch.encode("utf-8"), capture_output=True, timeout=15, check=False,
            )
            if check.returncode:
                return check.stderr.decode("utf-8", "replace")[-4000:] or "Patch check failed in the preflight copy."
            apply = subprocess.run(
                ["git", "apply", "--recount", "--unidiff-zero", "-"], cwd=temp_root,
                input=patch.encode("utf-8"), capture_output=True, timeout=15, check=False,
            )
            if apply.returncode:
                return apply.stderr.decode("utf-8", "replace")[-4000:] or "Patch apply failed in the preflight copy."
            for name in paths:
                candidate = temp_root / name
                if candidate.suffix.lower() == ".py" and candidate.is_file():
                    try:
                        ast.parse(candidate.read_text(encoding="utf-8"), filename=name)
                    except (OSError, UnicodeError, SyntaxError) as exc:
                        return f"Python syntax check failed for {name}: {exc}"
    except (OSError, subprocess.SubprocessError) as exc:
        return f"Could not complete the D-drive patch preflight: {type(exc).__name__}: {exc}"
    return None


def propose_patch(root, patch):
    root = _workspace(root)
    if os.environ.get("ENABLE_CODE_WRITE") != "1":
        return {"error": "Patch application is disabled. Set ENABLE_CODE_WRITE=1 only for a trusted, isolated workspace."}
    if not isinstance(patch, str) or len(patch) > 1_000_000 or "GIT binary patch" in patch:
        return {"error": "Patch must be text and no larger than 1 MB."}
    patch = _normalize_model_patch(patch)
    try:
        paths = _patch_paths(patch)
        for name in paths:
            destination = root / name
            resolved = Path(os.path.realpath(os.path.abspath(os.fspath(destination))))
            if not resolved.is_relative_to(root):
                raise ValueError("Patch may not write through a symbolic link outside CODE_WORKSPACE.")
        preflight_error = _preflight_patch(root, patch, paths)
        if preflight_error:
            return {"error": "Patch preflight failed; workspace files were not changed.",
                    "detail": preflight_error}
        check = subprocess.run(["git", "apply", "--recount", "--unidiff-zero", "--check", "-"], cwd=root, input=patch.encode("utf-8"),
                               capture_output=True, timeout=15, check=False)
        if check.returncode:
            detail = check.stderr.decode("utf-8", "replace")[-4000:]
            return {"error": "Patch check failed.", "detail": detail}
        apply = subprocess.run(["git", "apply", "--recount", "--unidiff-zero", "-"], cwd=root, input=patch.encode("utf-8"),
                               capture_output=True, timeout=15, check=False)
        if apply.returncode:
            detail = apply.stderr.decode("utf-8", "replace")[-4000:]
            return {"error": "Patch application failed.", "detail": detail}
        return {"applied": True, "files": paths, "message": "Patch applied; inspect the diff and run tests."}
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return {"error": str(exc)}


def replace_text(root, path, old_text, new_text):
    """Replace one exact, unique text block in a workspace file."""
    if os.environ.get("ENABLE_CODE_WRITE") != "1":
        return {"error": "Text replacement is disabled. Set ENABLE_CODE_WRITE=1 only for a trusted, isolated workspace."}
    if not isinstance(old_text, str) or not old_text or len(old_text) > 100_000:
        return {"error": "old_text must contain 1-100000 characters."}
    if not isinstance(new_text, str) or len(new_text) > 100_000:
        return {"error": "new_text must contain at most 100000 characters."}
    root = _workspace(root)
    try:
        target = _safe_path(root, path)
        original = target.read_text(encoding="utf-8")
        count = original.count(old_text)
        if count != 1:
            return {"error": f"Expected old_text to match exactly once; found {count} matches."}
        updated = original.replace(old_text, new_text, 1)
        if target.suffix.lower() == ".py":
            try:
                compile(updated, str(target), "exec")
            except SyntaxError as exc:
                return {"error": "Replacement rejected: resulting Python file does not compile.",
                        "line": exc.lineno, "detail": exc.msg}
        _atomic_write_text(target, updated)
        return {"applied": True, "path": target.relative_to(root).as_posix(),
                "message": "Exact text replacement applied once; inspect the diff and run tests."}
    except (OSError, UnicodeError, ValueError) as exc:
        return {"error": str(exc)}


def run_tests(root, test_path="."):
    root = _workspace(root)
    if os.environ.get("ENABLE_CODE_EXECUTION") != "1":
        return {"error": "Test execution is disabled. Enable it only when CODE_WORKSPACE is mounted into an isolated Docker environment."}
    relative = Path(str(test_path))
    if relative.is_absolute() or ".." in relative.parts:
        return {"error": "test_path must stay inside CODE_WORKSPACE"}
    image = os.environ.get("CODE_SANDBOX_IMAGE", "python:3.12-slim")
    command = ["docker", "run", "--rm", "--network=none", "--read-only", "--memory=3g", "--cpus=2",
               "--pids-limit=128", "--tmpfs", "/tmp:rw,nosuid,nodev,size=512m",
               "-v", f"{root}:/workspace:ro", "-w", "/workspace", image,
               "python", "-m", "pytest", "-q", "-p", "no:cacheprovider", relative.as_posix()]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False,
                                env={"PATH": os.environ.get("PATH", ""), "DOCKER_CONFIG": os.environ.get("DOCKER_CONFIG", "")})
    except (OSError, subprocess.SubprocessError) as exc:
        return {"error": f"Sandboxed test run failed: {type(exc).__name__}"}
    return {"passed": result.returncode == 0, "exit_code": result.returncode,
            "stdout": result.stdout[-8000:], "stderr": result.stderr[-4000:]}
