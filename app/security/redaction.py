"""
Second redaction pass — runs on anything about to reach an LLM, Slack, or a
PR body. Unlike the OTel Collector's regex-only first pass, this one can
afford real logic, in particular an actual Luhn checksum for card numbers
instead of "any 13-19 digit run," which avoids falsely redacting things like
trace IDs that merely happen to be the same length as a card number.

Redaction runs in a fixed order: structured patterns (a DSN password, a JWT)
are matched before the generic card-number pass gets a chance to
misinterpret their digit substrings.

  1. Password in a URL/DSN: scheme://user:PASSWORD@host -> scheme://user:<secret>@host.
     Only the password is replaced; scheme, user, and host are kept.
  2. Query-string secrets: ?token=X, &password=X, &secret=X, &api_key=X
     (case-insensitive key) -> X replaced with <secret>. Other params untouched.
  3. Bearer tokens: "Bearer <token>" -> "<secret>".
  4. JWTs: three base64url segments separated by dots, first segment starting
     with "eyJ" (base64 of '{"') -> <secret>.
  5. Known API key prefixes (sk-, ghp_, github_pat_, xox, AKIA) -> <secret>.
  6. Emails -> <email>.
  7. Card numbers: a run of 13-19 digits (optionally separated by spaces or
     dashes) that passes the Luhn checksum -> <card>. A same-length digit run
     that fails Luhn is left untouched.

Luhn check (step 7): starting from the rightmost digit, double every second
digit; if a doubled digit exceeds 9, subtract 9. Sum all digits (doubled and
undoubled). Valid if the sum is divisible by 10.
"""


import re

_DSN_PASSWORD_RE = re.compile(r"(://[^:/\s@]+:)([^@/\s]+)(@)")
_QUERY_SECRET_RE = re.compile(r"(?i)\b(token|password|secret|api_key)=([^&\s]+)")
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9\-_.]+")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_API_KEY_RE = re.compile(r"\b(?:sk-|ghp_|github_pat_|xox[a-zA-Z]?-?|AKIA)[A-Za-z0-9_-]+\b")
_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
# Digits with an optional single space/dash between each pair — how a card
# number actually gets written in a validation error, a CSV export, or a
# user-facing message ("4111-1111-1111-1111"), not just as one solid run.
# Total digit count (separators don't count) is still constrained to 13-19.
_CARD_CANDIDATE_RE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")


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
        digits = re.sub(r"[ -]", "", match.group(0))
        return "<card>" if _luhn_valid(digits) else match.group(0)

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
