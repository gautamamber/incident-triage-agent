import ast
import re
from pathlib import Path

MAX_READ_LINES = 400
MAX_SEARCH_RESULTS = 50


def _confine(repo_path: Path, relative: str) -> Path:
    """Resolves `relative` against repo_path and refuses anything that
    escapes it — no `..`, no symlink pointing outside. Same rule as
    git_repo.py's fixed-cwd subprocess calls: the caller controls the target
    file/pattern, never the boundary."""
    resolved = (repo_path / relative).resolve()
    if not resolved.is_relative_to(repo_path.resolve()):
        raise ValueError(f"path {relative!r} escapes the repo root")
    return resolved


def _iter_py_files(repo_path: Path):
    for py_file in repo_path.rglob("*.py"):
        if ".venv" in py_file.parts or "__pycache__" in py_file.parts:
            continue
        yield py_file


def search_code(repo_path: Path, pattern: str, glob: str = "*.py") -> str:
    """Regex search across the repo (doc section 7.2's search_code) — pure
    Python instead of shelling out to ripgrep, since this machine doesn't
    have it installed and this project avoids adding dependencies the user
    hasn't explicitly asked for."""
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return f"invalid pattern: {exc}"

    matches = []
    for file in repo_path.rglob(glob):
        if ".venv" in file.parts or "__pycache__" in file.parts or not file.is_file():
            continue
        try:
            for lineno, line in enumerate(file.read_text().splitlines(), 1):
                if regex.search(line):
                    rel = file.relative_to(repo_path)
                    matches.append(f"{rel}:{lineno}:{line}")
                    if len(matches) >= MAX_SEARCH_RESULTS:
                        return "\n".join(matches)
        except UnicodeDecodeError:
            continue
    return "\n".join(matches) if matches else "no matches"


def read_file(repo_path: Path, path: str, start_line: int = 1, end_line: int | None = None) -> str:
    resolved = _confine(repo_path, path)
    if not resolved.is_file():
        return f"no such file: {path}"
    all_lines = resolved.read_text().splitlines()
    end = end_line or len(all_lines)
    if end - start_line + 1 > MAX_READ_LINES:
        end = start_line + MAX_READ_LINES - 1
    numbered = [
        f"{i}: {line}" for i, line in enumerate(all_lines[start_line - 1 : end], start_line)
    ]
    return "\n".join(numbered)


def find_function(repo_path: Path, name: str) -> str:
    """Python `ast`-based search for a function/method definition (doc
    section 7.2 — tree-sitter for other languages is a later phase; this
    demo repo is Python-only, see the note in app/evidence.py)."""
    matches = []
    for py_file in _iter_py_files(repo_path):
        try:
            tree = ast.parse(py_file.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name:
                rel = py_file.relative_to(repo_path)
                matches.append(f"{rel}:{node.lineno}")
    return "\n".join(matches) if matches else f"no function named {name!r} found"


def find_references(repo_path: Path, symbol: str) -> str:
    """Every place `symbol` appears as a whole word — a plainer, faster
    stand-in for real call-graph analysis."""
    word_re = re.compile(rf"\b{re.escape(symbol)}\b")
    matches = []
    for py_file in _iter_py_files(repo_path):
        try:
            for lineno, line in enumerate(py_file.read_text().splitlines(), 1):
                if word_re.search(line):
                    rel = py_file.relative_to(repo_path)
                    matches.append(f"{rel}:{lineno}:{line}")
                    if len(matches) >= MAX_SEARCH_RESULTS:
                        return "\n".join(matches)
        except UnicodeDecodeError:
            continue
    return "\n".join(matches) if matches else "no references found"
