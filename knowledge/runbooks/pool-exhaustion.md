# Connection pool exhaustion

**Category:** DATABASE
**Typical exception:** TimeoutError ("QueuePool limit ... reached, connection timed out")

## Symptoms
- Requests succeed fine at first, then start failing after a burst of traffic
- The failure message explicitly mentions pool size, overflow, or a
  connection checkout timeout
- Unrelated endpoints start failing too once the pool is fully exhausted —
  the timeout isn't specific to one query, it's a resource shortage

## Common causes
- A code path opens a raw connection or session and never closes it —
  commonly a manually-opened `engine.connect()` or `Session()` outside the
  normal request-scoped dependency pattern
- An exception path skips a `finally`/`with` block that would have released
  the connection
- A reference to the connection object is accidentally retained somewhere
  (e.g. appended to a module-level list), preventing garbage collection from
  reclaiming it even after the request ends

## How to confirm
- Check whether the affected endpoint opens any connection outside the
  standard dependency-injected session
- Look for a recent commit that added a new query/probe to a hot code path

## Recommended action
- The fix is almost always a missing `with`/`finally` around a raw
  connection — either revert the offending commit or add proper connection
  cleanup
