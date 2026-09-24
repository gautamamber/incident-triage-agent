import subprocess
from dataclasses import dataclass
from pathlib import Path

MAX_DIFF_LINES = 400


@dataclass
class CommitInfo:
    sha: str
    author: str
    timestamp: str
    message: str
    files: list[str]


def _run_git(repo_path: Path, args: list[str]) -> str:
    # Fixed argument list, no shell=True, cwd pinned to the resolved repo path —
    # repo_path always comes from repo_registry (config-resolved, never from
    # anything an LLM could influence, per the diff-policy spirit in section 11.4).
    result = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def recent_commits(
    repo_path: Path, since_hours: int = 48, paths: list[str] | None = None
) -> list[CommitInfo]:
    """Commits in the lookback window, optionally confined to specific paths
    (section 7.2). Used to correlate a code change with when an incident
    started — the whole point of git-history-as-evidence (section 6.3)."""
    args = [
        "log",
        f"--since={since_hours} hours ago",
        "--pretty=format:COMMIT %H|%an|%aI|%s",
        "--name-only",
    ]
    if paths:
        args += ["--", *paths]

    output = _run_git(repo_path, args)
    if not output.strip():
        return []

    commits = []
    blocks = output.split("COMMIT ")[1:]  # first split chunk is empty
    for block in blocks:
        header, *file_lines = block.strip().splitlines()
        sha, author, timestamp, message = header.split("|", 3)
        files = [f for f in file_lines if f.strip()]
        commits.append(
            CommitInfo(sha=sha, author=author, timestamp=timestamp, message=message, files=files)
        )
    return commits


def current_sha(repo_path: Path) -> str:
    """HEAD commit — pinned by load_context so a run is reproducible even if
    the repo moves on while the investigation is still going (section 6.3)."""
    return _run_git(repo_path, ["rev-parse", "HEAD"]).strip()


def git_diff(repo_path: Path, sha: str, max_lines: int = MAX_DIFF_LINES) -> str:
    """Diff of one commit, size-capped (section 7.2)."""
    output = _run_git(repo_path, ["show", "--stat", "-p", sha])
    lines = output.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... truncated ({len(lines) - max_lines} more lines)"]
    return "\n".join(lines)
