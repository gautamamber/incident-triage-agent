# Database query timeout

**Category:** DATABASE
**Typical exception:** TimeoutError, OperationalError, QueryCanceled

## Symptoms
- Requests fail after a fixed delay (matches `statement_timeout`)
- Trace shows the database component dominating request latency (often >80%)
- Errors cluster around one endpoint or query pattern

## Common causes
- Missing index on a column used in a WHERE/JOIN clause, forcing a sequential
  scan over a large table
- A query that used to be selective became broad after a WHERE clause change
- Table grew large enough that a previously-fast scan is no longer fast

## How to confirm
- Check `EXPLAIN ANALYZE` on the query — a `Seq Scan` over a large table with
  a low `rows` estimate relative to the table size is the classic signature
- Compare row counts / index list before and after the incident's suspect
  commit or the last known-good deploy

## Recommended action
- If a recent commit removed an index or changed the query shape: revert if
  possible, or add the missing index back
- If no application commit is responsible (e.g. an index was dropped as a
  manual DB operation), this is a **NO_CODE_FIX** — flag for a human to run
  the index migration, do not attempt a code revert
