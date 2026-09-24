"""
Exercise: implement error fingerprinting (architecture doc section 5.2).

normalize_message(message) must replace, in this order (order matters — e.g. a
UUID contains hex characters and digits, so it must be matched before the
plainer hex/number patterns would wrongly chew it up piecemeal):

    UUIDs                    -> <uuid>
    hex strings, 8+ chars    -> <hex>
    emails                   -> <email>
    IPv4 addresses           -> <ip>
    ISO timestamps/dates     -> <ts>
    quoted strings           -> <str>      (single or double quoted)
    integers and decimals    -> <num>
    repeated whitespace      -> single space

Run the tests as you go: `uv run pytest tests/unit/detector/test_fingerprint.py -v`
They pin down the exact patterns expected — e.g. "30 seconds" -> "<num> seconds",
not "<num><num>" or similar. Use the `re` module.

fingerprint(service, exception_type, message, top_frame) must:
  1. Call normalize_message(message).
  2. Concatenate: service + (exception_type or "none") + normalized_message + (top_frame or "none")
  3. Return the hex sha1 digest of that concatenation (`hashlib.sha1(...).hexdigest()`).

Two log lines that differ only in their variable parts (a UUID, a number, a
timestamp) must produce the identical fingerprint — that's the whole point:
it's what lets the aggregator (Phase 3's next file) count "Payment not found: <uuid>"
occurring 50 times as ONE recurring problem instead of 50 unrelated ones.
"""

import hashlib
import re

_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
    r"|\b\d{4}-\d{2}-\d{2}\b"
)
_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
_IPV4_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
_HEX_RE = re.compile(r"\b[0-9a-fA-F]{8,}\b")
_QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
_NUM_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_message(message: str) -> str:
    message = _UUID_RE.sub("<uuid>", message)
    message = _TIMESTAMP_RE.sub("<ts>", message)
    message = _EMAIL_RE.sub("<email>", message)
    message = _IPV4_RE.sub("<ip>", message)
    message = _HEX_RE.sub("<hex>", message)
    message = _QUOTED_RE.sub("<str>", message)
    message = _NUM_RE.sub("<num>", message)
    message = _WHITESPACE_RE.sub(" ", message)
    return message.strip()


def fingerprint(
    service: str,
    exception_type: str | None,
    message: str,
    top_frame: str | None,
) -> str:
    normalized = normalize_message(message)
    raw = service + (exception_type or "none") + normalized + (top_frame or "none")
    return hashlib.sha1(raw.encode()).hexdigest()
