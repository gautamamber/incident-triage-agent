#!/usr/bin/env bash
# Runs the whole S01 pipeline end to end: bug -> traffic -> detect -> (LLM) investigate -> notify.
# Always leaves demo-payment-service back on `main` when it exits, even on failure.
set -euo pipefail

AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_DIR="$(cd "$AGENT_DIR/../demo-payment-service" && pwd)"
DEMO_URL="http://127.0.0.1:8800"
DURATION_SECONDS="${DURATION_SECONDS:-10}"
RPS="${RPS:-5}"

step() { echo; echo "=== $1 ==="; }

cleanup() {
  step "Cleanup: demo-payment-service back to main"
  cd "$DEMO_DIR" && git checkout main >/dev/null 2>&1 || true
  cd "$AGENT_DIR" && docker compose build demo-payment-service >/dev/null 2>&1
  docker compose up -d demo-payment-service >/dev/null 2>&1
}
trap cleanup EXIT

cd "$AGENT_DIR"

step "1/7 Starting the stack (Postgres, observability, demo service)"
docker compose up -d

step "2/7 Waiting for demo-payment-service to be healthy"
for _ in $(seq 1 30); do
  curl -sf "$DEMO_URL/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -sf "$DEMO_URL/health" >/dev/null || { echo "demo-payment-service never became healthy"; exit 1; }

step "3/7 Injecting S01 bug (bug/S01-null-refund branch) and rebuilding"
cd "$DEMO_DIR" && git checkout bug/S01-null-refund
cd "$AGENT_DIR" && docker compose build demo-payment-service && docker compose up -d demo-payment-service
for _ in $(seq 1 30); do
  curl -sf "$DEMO_URL/health" >/dev/null 2>&1 && break
  sleep 1
done

step "4/7 Generating crash traffic (${DURATION_SECONDS}s at ${RPS} rps)"
uv run python eval/traffic/refund_payments.py --duration-seconds "$DURATION_SECONDS" --rps "$RPS"

step "5/7 Running the detector"
INCIDENT_KEY=$(uv run python -c "
from app.db import SessionLocal, init_db
from app.detector.poller import poll_once
from app.models.incident import Incident, IncidentStatus

init_db()
db = SessionLocal()
poll_once(db, 'payment-service')
incident = (
    db.query(Incident)
    .filter(Incident.status.in_([IncidentStatus.OPEN.value, IncidentStatus.REOPENED.value]))
    .order_by(Incident.first_seen.desc())
    .first()
)
db.close()
print(incident.key if incident else '')
")

if [ -z "$INCIDENT_KEY" ]; then
  echo "No incident opened — traffic may not have crossed the detection threshold. Stopping here."
  exit 1
fi
echo "Detector opened: $INCIDENT_KEY"

step "6/7 Evidence bundle (no LLM)"
uv run python -m app.debug evidence "$INCIDENT_KEY"

if ! grep -q "^LLM_GATEWAY_API_KEY=.\+" .env 2>/dev/null && ! grep -q "^ANTHROPIC_API_KEY=.\+" .env 2>/dev/null; then
  echo
  echo "No LLM credentials set in .env (LLM_GATEWAY_API_KEY or ANTHROPIC_API_KEY) —"
  echo "skipping step 7 (worker: classify + RCA + notify). Add a key and re-run this"
  echo "script, or run manually: uv run python -m app.worker $INCIDENT_KEY"
  exit 0
fi

step "7/7 Running the worker (classify + RCA via LLM, then notify)"
uv run python -m app.worker "$INCIDENT_KEY"

echo
echo "Done. $INCIDENT_KEY is now RCA_READY (or NEEDS_HUMAN if the LLM step failed)."
echo "Check Slack for the alert, or: uv run python -m app.debug evidence $INCIDENT_KEY"
