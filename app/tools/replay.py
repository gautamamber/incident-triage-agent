import re
import subprocess
import time
from pathlib import Path

import httpx

# The project's own Compose network — the replay container joins it so it can
# reach the real postgres/fraud-mock services, same as demo-payment-service
# itself does. Optional validation (doc section 9.3): on top of, not instead
# of, the sandbox's --network none pytest+ruff checks, since serving real
# traffic needs a real network the sandbox deliberately doesn't have.
NETWORK = "incident-triage-agent_default"
_STATUS_5XX_RE = re.compile(r"\b5\d\d\b")


class ReplayError(RuntimeError):
    pass


def build_replay_image(scratch_dir: Path, dockerfile: Path, tag: str) -> None:
    result = subprocess.run(
        ["docker", "build", "-f", str(dockerfile), "-t", tag, str(scratch_dir)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise ReplayError(f"replay image build failed: {result.stderr.strip()}")


def _wait_for_health(port: int, timeout: int = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=2).raise_for_status()
            return
        except Exception:
            time.sleep(1)
    raise ReplayError("replay service never became healthy")


def deploy_and_replay(
    image_tag: str,
    traffic_script: Path,
    agent_root: Path,
    port: int = 18091,
    replay_seconds: int = 10,
    rps: float = 5,
) -> tuple[bool, str]:
    """Runs the fixed code as a real service on the project's own Docker
    network and replays the same traffic pattern that originally triggered
    the incident. Returns (healthy, raw_traffic_output) — `healthy` is False
    if any 5xx showed up in the replayed traffic's status breakdown."""
    container_name = f"replay-{int(time.time())}"
    subprocess.run(
        [
            "docker", "run", "-d", "--rm", "--name", container_name,
            "--network", NETWORK,
            "-p", f"127.0.0.1:{port}:8000",
            "-e", "DATABASE_URL=postgresql+psycopg://agent:agent@postgres:5432/payments",
            "-e", "FRAUD_MOCK_URL=http://fraud-mock:8010",
            image_tag,
        ],  # fmt: skip
        check=True,
        capture_output=True,
        timeout=30,
    )
    try:
        _wait_for_health(port)
        result = subprocess.run(
            [
                "uv", "run", "python", str(traffic_script),
                "--base-url", f"http://127.0.0.1:{port}",
                "--duration-seconds", str(replay_seconds), "--rps", str(rps),
            ],  # fmt: skip
            cwd=agent_root,
            capture_output=True,
            text=True,
            timeout=replay_seconds + 30,
        )
        output = result.stdout + result.stderr
        if "status breakdown:" in output:
            status_section = output.split("status breakdown:")[-1]
        else:
            status_section = output
        healthy = not _STATUS_5XX_RE.search(status_section)
        return healthy, output
    finally:
        subprocess.run(["docker", "stop", container_name], capture_output=True, timeout=15)
