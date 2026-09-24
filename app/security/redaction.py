"""
Exercise: the second redaction pass (architecture doc section 11.3) — runs on
anything about to reach an LLM, Slack, or a PR body. Unlike the OTel Collector's
regex-only first pass (Phase 1), this one can afford real logic, in particular
an actual Luhn checksum for card numbers instead of "any 13-19 digit run" —
which is exactly the pattern that falsely mangled a trace ID back in Phase 1.

Implement, in this order (order matters — redact structured patterns like a
DSN password or a JWT before the generic card-number pass gets a chance to
misinterpret their digit substrings):

  1. Password in a URL/DSN: scheme://user:PASSWORD@host -> scheme://user:<secret>@host
     Keep the scheme, user, and host. Only the password is replaced.

  2. Query-string secrets: ?token=X, &password=X, &secret=X, &api_key=X (case-insensitive
     key) -> replace X with <secret>. Leave other query params alone.

  3. Bearer tokens: "Bearer <token>" -> "<secret>" (replaces the whole "Bearer ..." span).

  4. JWTs: three base64url segments separated by dots, first segment starts with
     "eyJ" (base64 of '{"') -> <secret>.

  5. Known API key prefixes: sk-, ghp_, github_pat_, xox, AKIA, each followed by
     alphanumerics/-/_ -> <secret>.

  6. Emails -> <email>.

  7. Card numbers: a run of 13-19 digits that passes the Luhn checksum -> <card>.
     A same-length digit run that FAILS Luhn must be left untouched — that's the
     test that proves this pass is better than Phase 1's collector regex.

Luhn check, for step 7: starting from the rightmost digit, double every second
digit; if a doubled digit exceeds 9, subtract 9. Sum all digits (doubled and
undoubled). Valid if the sum is divisible by 10. Write this as its own small
helper — it's the one genuinely new algorithm in this exercise, worth pulling
out and testing in isolation.

Run: `uv run pytest tests/unit/security/test_redaction.py -v`
"""


import re

_DSN_PASSWORD_RE = re.compile(r"(://[^:/\s@]+:)([^@/\s]+)(@)")
_QUERY_SECRET_RE = re.compile(r"(?i)\b(token|password|secret|api_key)=([^&\s]+)")
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9\-_.]+")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_API_KEY_RE = re.compile(r"\b(?:sk-|ghp_|github_pat_|xox[a-zA-Z]?-?|AKIA)[A-Za-z0-9_-]+\b")
_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
_CARD_CANDIDATE_RE = re.compile(r"\b\d{13,19}\b")


def _luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _redact_cards(text: str) -> str:
    def replace(match: re.Match) -> str:
        return "<card>" if _luhn_valid(match.group(0)) else match.group(0)

    return _CARD_CANDIDATE_RE.sub(replace, text)


def redact(text: str) -> str:
    text = _DSN_PASSWORD_RE.sub(r"\1<secret>\3", text)
    text = _QUERY_SECRET_RE.sub(lambda m: f"{m.group(1)}=<secret>", text)
    text = _BEARER_RE.sub("<secret>", text)
    text = _JWT_RE.sub("<secret>", text)
    text = _API_KEY_RE.sub("<secret>", text)
    text = _EMAIL_RE.sub("<email>", text)
    text = _redact_cards(text)
    return text
