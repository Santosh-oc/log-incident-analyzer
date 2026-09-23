"""JSON-lines log file parser.

Pure parsing logic — no database or LLM imports.
"""
import gzip
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import BinaryIO, Iterable

TIMESTAMP_KEYS = ("ts", "timestamp", "time", "@timestamp")
LEVEL_KEYS = ("level", "severity", "lvl", "log.level")
SERVICE_KEYS = ("service", "app", "logger", "component")
MESSAGE_KEYS = ("msg", "message", "text")

LEVEL_MAP = {
    "debug": "DEBUG",
    "info": "INFO",
    "notice": "INFO",
    "warn": "WARN",
    "warning": "WARN",
    "error": "ERROR",
    "err": "ERROR",
    "fatal": "FATAL",
    "critical": "FATAL",
    "crit": "FATAL",
    "panic": "FATAL",
}

MAX_UNPARSED_SAMPLES = 10


@dataclass
class ParsedEvent:
    line_number: int
    timestamp: datetime
    level: str
    service: str
    message: str


@dataclass
class ParseResult:
    events: list[ParsedEvent] = field(default_factory=list)
    total_lines: int = 0
    unparsed_lines: int = 0
    unparsed_samples: list[int] = field(default_factory=list)

    @property
    def parsed_events(self) -> int:
        return len(self.events)


def _first_key(obj: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]
    return None


def normalize_level(raw) -> str:
    if not isinstance(raw, str):
        return "INFO"
    return LEVEL_MAP.get(raw.strip().lower(), "INFO")


def parse_timestamp(raw):
    """Parse ISO-8601 strings or Unix epoch seconds/milliseconds.

    Naive timestamps are treated as UTC. Returns None if unparseable.
    """
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        value = float(raw)
        # Heuristic: milliseconds are 13+ digits (post-2001 in seconds is 10 digits).
        if abs(value) >= 1e11:
            value /= 1000.0
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        # Numeric string → epoch.
        try:
            value = float(text)
        except ValueError:
            pass
        else:
            if abs(value) >= 1e11:
                value /= 1000.0
            try:
                return datetime.fromtimestamp(value, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None
        iso = text
        if iso.endswith(("Z", "z")):
            iso = iso[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(iso)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _iter_lines(data: bytes) -> Iterable[tuple[int, str]]:
    """Yield (line_number, line) pairs, decompressing gzip when needed."""
    if data[:2] == b"\x1f\x8b":
        stream = io.TextIOWrapper(gzip.GzipFile(fileobj=io.BytesIO(data)), encoding="utf-8", errors="replace")
    else:
        stream = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8", errors="replace")
    with stream:
        for line_number, line in enumerate(stream, start=1):
            yield line_number, line.rstrip("\n").rstrip("\r")


def parse_jsonl(data: bytes) -> ParseResult:
    """Parse JSON-lines bytes into events. Never raises on bad lines."""
    result = ParseResult()
    for line_number, line in _iter_lines(data):
        if not line.strip():
            continue  # blank lines are skipped and not counted
        result.total_lines += 1
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            obj = None
        if not isinstance(obj, dict):
            _mark_unparsed(result, line_number)
            continue
        raw_ts = _first_key(obj, TIMESTAMP_KEYS)
        raw_msg = _first_key(obj, MESSAGE_KEYS)
        ts = parse_timestamp(raw_ts)
        message = raw_msg if isinstance(raw_msg, str) else (str(raw_msg) if raw_msg is not None else None)
        if ts is None or not message:
            _mark_unparsed(result, line_number)
            continue
        raw_level = _first_key(obj, LEVEL_KEYS)
        raw_service = _first_key(obj, SERVICE_KEYS)
        service = raw_service if isinstance(raw_service, str) and raw_service.strip() else "unknown"
        result.events.append(
            ParsedEvent(
                line_number=line_number,
                timestamp=ts,
                level=normalize_level(raw_level),
                service=service,
                message=message,
            )
        )
    return result


def _mark_unparsed(result: ParseResult, line_number: int) -> None:
    result.unparsed_lines += 1
    if len(result.unparsed_samples) < MAX_UNPARSED_SAMPLES:
        result.unparsed_samples.append(line_number)
