import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent.parent.parent
DOCKERFILE = AGENT_ROOT / "sandbox" / "Dockerfile.runner"

# command_id -> fixed argument list. No free-form commands ever reach the
# sandbox — the LLM can request one of these three names, never arbitrary
# shell text.
_ALLOWED_COMMANDS: dict[str, list[str]] = {
    "pytest_all": ["python", "-m", "pytest", "-q"],
    "pytest_file": ["python", "-m", "pytest", "-q"],  # a path gets appended by the caller
    "ruff": ["ruff", "check", "."],
}


@dataclass
class SandboxResult:
    command_id: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def _lockfile_hash(repo_path: Path) -> str:
    lockfile = repo_path / "uv.lock"
    if not lockfile.exists():
        lockfile = repo_path / "pyproject.toml"
    return hashlib.sha256(lockfile.read_bytes()).hexdigest()[:12]


def _image_exists(tag: str) -> bool:
    result = subprocess.run(["docker", "images", "-q", tag], capture_output=True, text=True)
    return bool(result.stdout.strip())


def ensure_sandbox_image(repo_path: Path) -> str:
    """Builds `incident-agent-runner:<lockfile-hash>` if it doesn't already
    exist for this exact dependency set — built once from the repo's own
    checkout (diff_policy forbids a patch touching pyproject.toml/uv.lock,
    so the lockfile never changes across fix attempts), then reused across
    every validation run."""
    tag = f"incident-agent-runner:{_lockfile_hash(repo_path)}"
    if _image_exists(tag):
        return tag

    result = subprocess.run(
        ["docker", "build", "-f", str(DOCKERFILE), "-t", tag, str(repo_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"sandbox image build failed:\n{result.stderr}")
    return tag


def run_in_sandbox(
    worktree: Path, image_tag: str, command_id: str, file: str | None = None, timeout: int = 300
) -> SandboxResult:
    """Runs one allowlisted command in a locked-down container: no network,
    read-only filesystem except the mounted worktree and /tmp, capped
    CPU/memory/processes, non-root, no privilege escalation, no Docker
    socket mounted in."""
    if command_id not in _ALLOWED_COMMANDS:
        raise ValueError(f"unknown command_id {command_id!r}")

    cmd = list(_ALLOWED_COMMANDS[command_id])
    if command_id == "pytest_file":
        if not file:
            raise ValueError("pytest_file requires `file`")
        cmd.append(file)

    docker_cmd = [
        "docker", "run", "--rm",
        "--network", "none",
        "--read-only", "--tmpfs", "/tmp:rw,size=256m",
        "--cpus", "1", "--memory", "1g", "--pids-limit", "256",
        "--user", "1000:1000", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "-v", f"{worktree}:/work:rw",
        "-w", "/work",
        image_tag,
        *cmd,
    ]  # fmt: skip

    try:
        result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return SandboxResult(
            command_id=command_id,
            returncode=-1,
            stdout=exc.stdout or "",
            stderr=f"sandbox run exceeded {timeout}s timeout",
        )

    return SandboxResult(
        command_id=command_id,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
