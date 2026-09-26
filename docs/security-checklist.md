# Security checklist — doc section 11 review

Walkthrough of every threat/control in [architecture-and-workflow.md §11](architecture-and-workflow.md),
verified against the actual code (not the doc's description of intent) on 2026-09-26.
Each row cites the exact file backing the claim, and lists what's real vs still open.

## 11.1 Threat model

| Threat | Control | Status | Evidence |
|---|---|---|---|
| Prompt injection via telemetry | Untrusted-data handling, no free-form tools, diff policy, draft PR only | ✅ Implemented, live-tested | `<untrusted>` wrapping + explicit ignore-instructions rule in [`app/security/untrusted.py`](../app/security/untrusted.py), applied in `classify.py`, `rca.py`, `code_investigation.py`, `fix.py`. Proven live: S07 scenario (`eval/scenarios/S07.yaml`) passes — injected text changes neither `category`, `fix_strategy`, nor the RCA's own wording. |
| Sensitive data sent to LLM | Redaction at collector and before every LLM call | ✅ Implemented, gaps found and fixed this review | `app/security/redaction.py`, called from `app/evidence.py`. This review found and fixed three real gaps: `build_log_evidence`'s summary line, `build_trace_evidence`'s `error_spans[].message`, and `build_git_evidence`'s non-latest commit messages were all reaching the LLM unredacted. Also added dash/space-formatted card number handling (`4111-1111-1111-1111` wasn't caught by the old digit-run-only regex). Covered by `tests/unit/test_evidence_redaction.py` and `tests/unit/security/test_redaction_realistic.py`. |
| Arbitrary code execution | Sandbox | ✅ Implemented, live-tested | `app/tools/sandbox.py` — `--network none --read-only --cap-drop ALL --security-opt no-new-privileges`, non-root, resource-capped, hard timeout. No Docker-socket mount anywhere in the codebase (verified via full-repo grep). Proven live repeatedly (Phase 10 tests). |
| Repository damage | Branch protection, token scope, diff policy | ✅ Implemented, live-tested | `app/security/diff_policy.py` (path/size/pattern whitelist, 8/8 unit tests + 2 live-loop integration tests). The GitHub token is scoped to Pull requests + Issues + Contents on one repo only (no admin, no other repos). The agent's own code never merges anything — `create_draft_pr` always passes `draft=True`; merge actions in this project were all done by a human or blocked outright by the Claude Code harness's own "merge without review" classifier when tried programmatically. |
| Credential leakage | Secrets handling | ✅ Implemented | `.env` is git-ignored (verified). Never echoed in any output this session — validated via API calls that only print status codes, never the token itself. |
| Cost / runaway loops | Aggregation, lifecycle, budgets, rate limits | ✅ Implemented, live-tested | All 8 budget controls in `config/policies.yaml`'s `budget:`/`fix:`/`investigation:` sections are enforced in code (`app/security/budget.py`, `app/worker.py`'s `AgentRunLog` rate limiter) — see the budget section below for the full breakdown. |
| Exposed local services | Bind to 127.0.0.1, internal Docker network | ✅ Implemented | Every service in `docker-compose.yml` binds `127.0.0.1:<port>:<port>` — verified directly (7/7 services). |

## 11.7 Budget / kill-switch table — verified control by control

| Control | Default | Status | Evidence |
|---|---|---|---|
| `AGENT_MODE` | `rca` | ✅ Enforced | `app/agents/nodes/route.py`'s `fix_eligibility()` reads `settings.agent_mode` directly — never anything LLM-derived. |
| Max LLM tokens per run | 150k | ✅ Enforced | `token_usage` accumulates via `Annotated[int, operator.add]` on `InvestigationState`; actively gates `code_investigation`'s tool loop and `fix.py`'s patch-retry loop (`app/security/budget.py`). |
| Max tool calls in code investigation | 12 | ✅ Enforced | `app/agents/nodes/code_investigation.py`, `policies.yaml`'s `investigation.max_code_tool_calls`. |
| Max fix attempts | 3 | ✅ Enforced | `app/agents/nodes/fix.py`'s retry loop, `policies.yaml`'s `fix.max_attempts`. |
| Max wall time per run | 10 min | ✅ Enforced | Same two loops check `wall_time_exceeded()` every iteration. |
| Max agent runs per hour | 10 | ✅ Enforced | New `agent_run_log` table (`app/models/incident.py`), checked in `app/worker.py` before claiming an incident. |
| Concurrent runs: 1 per incident | — | ✅ Enforced | Postgres advisory lock in `_claim_incident` (`app/worker.py`). |
| Concurrent runs: 2 total (global) | — | ❌ **Not enforced** | No global concurrency cap exists. Each `run_once` invocation is its own process with no coordination beyond the per-incident lock — nothing stops N incidents being investigated in parallel if N workers are started. |

## Gaps found, not fixed (out of the scope actually asked for)

- **§11.9 Audit trail — doesn't exist.** The doc describes a `tool_calls` table (run ID, node, tool, redacted arguments, result size, duration, status) recording every tool call. No such table exists — the only persistence is LangGraph's checkpointer, which stores full state snapshots per node, not a queryable per-tool-call log. This is real, new scope (instrumentation at every tool-call site across `code_investigation.py`, `git_repo.py`, `tempo.py`, `loki.py`, `prometheus.py`, and the sandbox calls in `fix.py`) — flagging it rather than building it silently.
- **Global concurrency cap (2 total)** — see table above.

## 11.6 Secrets and credentials — spot-checked, not re-audited line by line

`.env` git-ignored, token scoped narrowly, never echoed. Full line-by-line re-audit of every log statement for accidental credential leakage wasn't performed as part of this pass — the redaction fixes above cover the LLM-facing path, which was the actual risk surface tested.

## 11.10 Third-party tracing

LangSmith/`LANGCHAIN_TRACING_V2` isn't referenced anywhere in `.env`/`.env.example` — off by default by simple absence, consistent with the doc's requirement, though it was never explicitly wired up as an opt-in feature either.
