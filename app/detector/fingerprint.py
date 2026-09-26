"""
Error fingerprinting: groups log lines that differ only in their variable
parts (a UUID, a number, a timestamp) into one recurring problem instead of
counting each occurrence as unrelated. This is what lets the aggregator count
"Payment not found: <uuid>" occurring 50 times as one incident.

normalize_message(message) replaces, in this order (order matters — a UUID
contains hex characters and digits, so it must be matched before the plainer
hex/number patterns would wrongly chew it up piecemeal):

    UUIDs                    -> <uuid>
    hex strings, 8+ chars    -> <hex>
    emails                   -> <email>
    IPv4 addresses           -> <ip>
    ISO timestamps/dates     -> <ts>
    quoted strings           -> <str>      (single or double quoted)
    integers and decimals    -> <num>
    repeated whitespace      -> single space

fingerprint(service, exception_type, message, top_frame) normalizes the
message, concatenates service + (exception_type or "none") +
normalized_message + (top_frame or "none"), and returns the hex SHA1 digest
of that string.
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
