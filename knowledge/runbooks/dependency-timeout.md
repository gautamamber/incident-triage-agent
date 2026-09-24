# Downstream dependency timeout

**Category:** DEPENDENCY
**Typical exception:** ReadTimeout, ConnectTimeout, ConnectError

## Symptoms
- Errors correlate with calls to an external/downstream service, not the
  database
- Trace shows a client-side span (an outbound HTTP call) dominating latency,
  not a database component
- The failure rate on the calling service tracks the downstream service's
  own health, not a recent deploy of the calling service

## Common causes
- The downstream dependency itself is slow, degraded, or down
- No timeout was set on the outbound call, so a slow dependency blocks the
  request indefinitely instead of failing fast
- No circuit breaker / retry backoff, so every request pays the full latency
  of a struggling dependency instead of failing fast after the first few

## How to confirm
- Check the downstream service's own health/latency, not the calling
  service's recent commits
- If no recent commit in the calling service touches the code path, this is
  not a code regression

## Recommended action
- This is usually **NO_CODE_FIX** from the calling service's side — the
  dependency itself needs attention, or a timeout/circuit-breaker needs to
  be added (a genuine code change, but not a revert)
- Do not revert a commit just because it's recent if the trace clearly shows
  the time is spent in the downstream call, not in the calling service's own
  logic
