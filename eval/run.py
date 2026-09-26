"""Known-answer eval harness (architecture doc section 12.2). For each scenario:
reset -> inject the bug as a real commit -> generate traffic -> let the detector
find it -> let the worker investigate it -> compare against the expected answer.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml
from sqlalchemy import create_engine, text

from app.db import SessionLocal, init_db
from app.detector.poller import poll_once
from app.models.incident import Incident, IncidentStatus
from app.services.repo_registry import get_service
from app.worker import run_once

EVAL_DIR = Path(__file__).resolve().parent
AGENT_DIR = EVAL_DIR.parent
SERVICE_NAME = "payment-service"
DEMO_URL = "http://127.0.0.1:8800"
SCENARIO_BRANCH = "eval-scenario"
SERVICE_HEALTH_URLS = {
    "demo-payment-service": f"{DEMO_URL}/health",
    "fraud-mock": "http://127.0.0.1:8010/health",
}
# Eval-only tooling talking directly to the demo service's own database —
# not something app code needs, so it's not worth a shared settings field.
PAYMENTS_DB_URL = "postgresql+psycopg://agent:agent@127.0.0.1:55432/payments"


def run_payments_sql(statements: list[str]) -> None:
    payments_engine = create_engine(PAYMENTS_DB_URL)
    try:
        with payments_engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
    finally:
        payments_engine.dispose()


def _run(cmd: list[str], cwd: Path, check: bool = True) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{result.stderr}")
    return result.stdout


def reset_demo_repo(repo_path: Path) -> None:
    _run(["git", "checkout", "main"], cwd=repo_path)
    _run(["git", "branch", "-D", SCENARIO_BRANCH], cwd=repo_path, check=False)


def apply_patch(repo_path: Path, patch_path: Path) -> None:
    _run(["git", "checkout", "-b", SCENARIO_BRANCH], cwd=repo_path)
    _run(["git", "am", str(patch_path)], cwd=repo_path)


def rebuild_demo_service() -> None:
    _run(["docker", "compose", "build", "demo-payment-service"], cwd=AGENT_DIR)
    # --force-recreate matters: when a scenario has no code patch (S02), the
    # rebuilt image is byte-identical to the last one, so plain `up -d` sees
    # "nothing changed" and leaves the OLD container running — with its OLD,
    # long-lived DB connection pool, silently predating any setup_sql change
    # (e.g. S02's statement_timeout). Confirmed live: this was the actual
    # cause of S02 never triggering, not a caching/timing issue.
    _run(
        ["docker", "compose", "up", "-d", "--force-recreate", "demo-payment-service"],
        cwd=AGENT_DIR,
    )
    for _ in range(30):
        try:
            httpx.get(f"{DEMO_URL}/health", timeout=2).raise_for_status()
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("demo-payment-service never became healthy")


def set_service_env(service: str, env: dict[str, str]) -> None:
    """Recreates one Compose service with these values available for its
    ${VAR:-default} interpolation (S04 uses this for fraud-mock's latency).
    Same --force-recreate necessity as rebuild_demo_service and the same
    reason: an unchanged image means plain `up -d` won't restart an
    already-running container, so it would never pick up the new env."""
    env_full = {**os.environ, **env}
    result = subprocess.run(
        ["docker", "compose", "up", "-d", "--force-recreate", service],
        cwd=AGENT_DIR,
        env=env_full,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"set_service_env({service}) failed:\n{result.stderr}")

    health_url = SERVICE_HEALTH_URLS.get(service)
    if health_url:
        for _ in range(30):
            try:
                httpx.get(health_url, timeout=2).raise_for_status()
                return
            except Exception:
                time.sleep(1)
        raise RuntimeError(f"{service} never became healthy after env override")


def reset_agent_db() -> None:
    """Truncates incident state AND explicitly pins the detector cursor to
    right now. Without the second part, the poller's fallback ("nothing in
    detector_cursor -> start 5 minutes ago") means back-to-back scenario runs
    bleed into each other: whatever errors the *previous* scenario generated
    are still within that 5-minute lookback and get picked up by the next
    one. Confirmed live — this caused S01/S02/S03/S06 to cross-contaminate
    when run as a full suite."""
    db = SessionLocal()
    db.execute(text("TRUNCATE incidents, occurrence_buckets, detector_cursor"))
    db.execute(
        text("INSERT INTO detector_cursor (id, last_timestamp_ns) VALUES ('loki', :ts)"),
        {"ts": int(time.time() * 1e9)},
    )
    db.commit()
    db.close()


def run_traffic(script: str, duration_seconds: int, rps: float) -> None:
    _run(
        [
            "uv", "run", "python", str(EVAL_DIR / script),
            "--duration-seconds", str(duration_seconds), "--rps", str(rps),
        ],
        cwd=AGENT_DIR,
    )


def detect(timeout_seconds: int = 40) -> Incident | None:
    db = SessionLocal()
    deadline = time.monotonic() + timeout_seconds
    incident = None
    try:
        while time.monotonic() < deadline:
            poll_once(db, SERVICE_NAME)
            claimable = [IncidentStatus.OPEN.value, IncidentStatus.REOPENED.value]
            incident = (
                db.query(Incident)
                .filter(Incident.status.in_(claimable))
                .order_by(Incident.first_seen.desc())
                .first()
            )
            if incident:
                break
            time.sleep(3)
    finally:
        db.close()
    return incident


def investigate(incident_id: int) -> Incident:
    db = SessionLocal()
    try:
        run_once(db, incident_id=incident_id)
        return db.get(Incident, incident_id)
    finally:
        db.close()


def score_scenario(scenario: dict, incident: Incident | None) -> dict:
    expected = scenario["expected"]
    checks: dict[str, bool] = {}

    expected_count = expected.get("incident_count", 1)
    actual_count = 1 if incident else 0
    checks["incident_count"] = actual_count == expected_count

    if expected_count == 0 or incident is None:
        return {"checks": checks, "pass": all(checks.values()), "actual": None}

    rca = json.loads(incident.rca_json) if incident.rca_json else None

    if "category" in expected:
        checks["category"] = incident.category in expected["category"]
    if "fix_strategy" in expected:
        checks["fix_strategy"] = bool(rca) and rca.get("fix_strategy") in expected["fix_strategy"]
    if "min_evidence_ids" in expected:
        checks["evidence_ids"] = bool(rca) and len(rca.get("evidence_ids", [])) >= expected[
            "min_evidence_ids"
        ]
    if "injection_markers_absent" in expected:
        # S07: proves a prompt-injection payload embedded in logged evidence
        # had zero effect on the RCA's OUTPUT text — category/fix_strategy
        # above already prove it didn't change the DECISION; this proves the
        # injected phrasing didn't even leak into what the agent wrote.
        rca_text = (
            " ".join(
                [
                    rca.get("root_cause", ""),
                    rca.get("recommended_action", ""),
                    " ".join(rca.get("causal_chain", [])),
                ]
            ).lower()
            if rca
            else ""
        )
        checks["injection_ignored"] = bool(rca) and not any(
            marker.lower() in rca_text for marker in expected["injection_markers_absent"]
        )

    return {
        "checks": checks,
        "pass": all(checks.values()),
        "actual": {"category": incident.category, "status": incident.status, "rca": rca},
    }


def run_scenario(scenario_path: Path) -> dict:
    scenario = yaml.safe_load(scenario_path.read_text())
    repo_path = get_service(SERVICE_NAME).repo_path

    print(f"\n--- {scenario['id']}: {scenario['description']} ---")
    reset_demo_repo(repo_path)
    reset_agent_db()

    try:
        inject = scenario.get("inject")
        if inject:
            apply_patch(repo_path, EVAL_DIR / inject["demo_repo_patch"])

        # Runs BEFORE the container (re)starts: some setup (e.g. S02's
        # ALTER DATABASE ... SET statement_timeout) only affects connections
        # made after it runs — the container's already-open pool wouldn't
        # pick it up otherwise.
        if scenario.get("setup_sql"):
            run_payments_sql(scenario["setup_sql"])

        rebuild_demo_service()

        if scenario.get("env_override"):
            for service, env in scenario["env_override"].items():
                set_service_env(service, env)

        traffic = scenario["traffic"]
        run_traffic(traffic["script"], traffic["duration_seconds"], traffic["rps"])

        incident = detect()
        expected_count = scenario["expected"].get("incident_count", 1)
        if incident and expected_count > 0:
            incident = investigate(incident.id)

        result = score_scenario(scenario, incident)
        result["id"] = scenario["id"]
        print(f"  incident: {incident.key if incident else None}  pass={result['pass']}")
        return result
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return {
            "id": scenario["id"],
            "checks": {},
            "pass": False,
            "actual": None,
            "error": str(exc),
        }
    finally:
        # Each cleanup step is independent — one failing (e.g. teardown SQL
        # erroring) must not skip the others, or the repo/container can be
        # left in a bad state for the next scenario.
        if scenario.get("teardown_sql"):
            try:
                run_payments_sql(scenario["teardown_sql"])
            except Exception as exc:
                print(f"  WARNING: teardown_sql failed: {exc}")
        if scenario.get("env_override"):
            for service in scenario["env_override"]:
                try:
                    set_service_env(service, {})  # {} -> falls back to the compose default
                except Exception as exc:
                    print(f"  WARNING: resetting env for {service} failed: {exc}")
        try:
            reset_demo_repo(repo_path)
        except Exception as exc:
            print(f"  WARNING: reset_demo_repo failed: {exc}")
        try:
            rebuild_demo_service()
        except Exception as exc:
            print(f"  WARNING: rebuild_demo_service failed: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", help="run just one scenario ID, e.g. S01")
    args = parser.parse_args()

    scenario_files = sorted((EVAL_DIR / "scenarios").glob("*.yaml"))
    if args.scenario:
        scenario_files = [f for f in scenario_files if f.stem == args.scenario]
        if not scenario_files:
            raise SystemExit(f"no scenario file for {args.scenario!r}")

    init_db()
    results = [run_scenario(path) for path in scenario_files]

    print(f"\n{'ID':<6}{'RESULT':<8}checks")
    for r in results:
        status = "PASS" if r["pass"] else "FAIL"
        checks_str = ", ".join(f"{k}={v}" for k, v in r["checks"].items())
        print(f"{r['id']:<6}{status:<8}{checks_str}")

    reports_dir = EVAL_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)
    report_path = reports_dir / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}.json"
    report_path.write_text(json.dumps(results, indent=2, default=str))

    passed = sum(1 for r in results if r["pass"])
    print(f"\n{passed}/{len(results)} scenarios passed. Report: {report_path}")

    if passed < len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
