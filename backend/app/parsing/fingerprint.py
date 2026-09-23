"""Message fingerprinting for incident grouping.

Pure functions only — no database or LLM imports, so this module is easy
to unit-test.
"""
import re

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)
_IP_RE = re.compile(
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
)
_HEX_RE = re.compile(r"\b[0-9a-f]{8,}\b", re.IGNORECASE)
_QUOTED_RE = re.compile(r'"[^"]*"|\'[^\']*\'')
_NUMBER_RE = re.compile(r"\d+")
_WHITESPACE_RE = re.compile(r"\s+")


def fingerprint(message: str) -> str:
    """Normalize a log message into a stable fingerprint.

    Order matters: lowercase first, then UUIDs, IPs, hex strings (8+ chars),
    quoted strings, and finally any remaining numbers. Whitespace is collapsed.
    """
    text = message.lower()
    text = _UUID_RE.sub("<uuid>", text)
    text = _IP_RE.sub("<ip>", text)
    text = _HEX_RE.sub("<hex>", text)
    text = _QUOTED_RE.sub("<str>", text)
    text = _NUMBER_RE.sub("<n>", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()
