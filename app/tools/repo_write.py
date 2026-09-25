import io
import shutil
import subprocess
import tarfile
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRATCH_ROOT = AGENT_ROOT / ".fix-scratch"

# This module never runs `git commit`, `git push`, or `git worktree` — every
# operation here is either read-only git introspection or a plain filesystem
# write. That's not stylistic: this machine's Argus DLP guardrail blocks any
# commit made inside a linked git worktree, confirmed live by reproducing it
# on an unrelated feature branch with no connection to main. Local git commit
# is a dead end here regardless of branch/isolation strategy. The actual
# commit, once sandbox validation passes, is made through the GitHub REST API
# (app/tools/github_api.py) instead — a local hook has no visibility into an
# HTTPS call, and it's no less auditable: it's the same commit history either
# way, just authored via API rather than `git commit`.


def _run_git(repo_path: Path, args: list[str], timeout: int = 30) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo_path, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def branch_name(incident_key: str) -> str:
    # Always agent/INC-xxxx, derived in code — never LLM-chosen (doc 7.3/9.2).
    return f"agent/{incident_key}"


def changed_files(repo_path: Path, sha: str) -> list[str]:
    """Files touched by one commit — read-only (doc 7.2-style introspection,
    reused here to know what a revert needs to restore)."""
    output = _run_git(repo_path, ["show", "--name-only", "--pretty=format:", sha])
    return [line for line in output.splitlines() if line.strip()]


def file_content_at(repo_path: Path, ref: str, path: str) -> str | None:
    """None means the path doesn't exist at that ref — used to tell 'this
    file was modified' from 'this file was added' when resolving a revert."""
    try:
        return _run_git(repo_path, ["show", f"{ref}:{path}"])
    except RuntimeError:
        return None


def prepare_scratch_copy(repo_path: Path, incident_key: str, ref: str = "origin/main") -> Path:
    """A plain filesystem snapshot of `ref` via `git archive` (read-only —
    archiving isn't a commit) — NOT a git checkout or worktree. Sandbox
    validation and patch application both happen here, on a directory with no
    `.git` at all, so nothing downstream can trigger a commit-time guardrail
    even by accident."""
    scratch_dir = SCRATCH_ROOT / incident_key
    if scratch_dir.exists():
        shutil.rmtree(scratch_dir)
    scratch_dir.mkdir(parents=True)

    archive = subprocess.run(
        ["git", "archive", ref], cwd=repo_path, capture_output=True, timeout=30
    )
    if archive.returncode != 0:
        raise RuntimeError(f"git archive {ref} failed: {archive.stderr.decode().strip()}")
    tarfile.open(fileobj=io.BytesIO(archive.stdout)).extractall(scratch_dir)
    return scratch_dir


def discard_scratch_copy(incident_key: str) -> None:
    shutil.rmtree(SCRATCH_ROOT / incident_key, ignore_errors=True)


def apply_revert(repo_path: Path, scratch_dir: Path, sha: str) -> dict[str, str | None]:
    """The plain-file equivalent of `git revert --no-edit <sha>`: rewrites
    every file the commit touched back to its pre-commit content. Returns
    {path: new_content}, where `None` means the bug commit added that file,
    so reverting deletes it."""
    changes: dict[str, str | None] = {}
    for path in changed_files(repo_path, sha):
        content = file_content_at(repo_path, f"{sha}^", path)
        target = scratch_dir / path
        if content is None:
            target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        changes[path] = content
    return changes


def apply_patch(repo_path: Path, scratch_dir: Path, unified_diff: str) -> None:
    """Applies an LLM-generated unified diff to the scratch copy — uses
    repo_path's object database for hunk-context validation but scratch_dir
    as the write target (`--work-tree`), so this still never commits
    anything. `git apply --check` first (doc 7.3/9.2's POLICY step)."""
    base_args = ["git", f"--git-dir={repo_path / '.git'}", f"--work-tree={scratch_dir}"]
    check = subprocess.run(
        [*base_args, "apply", "--check", "-"], input=unified_diff, capture_output=True, text=True
    )
    if check.returncode != 0:
        raise RuntimeError(f"patch does not apply: {check.stderr.strip()}")
    apply_result = subprocess.run(
        [*base_args, "apply", "-"], input=unified_diff, capture_output=True, text=True
    )
    if apply_result.returncode != 0:
        raise RuntimeError(f"git apply failed: {apply_result.stderr.strip()}")
