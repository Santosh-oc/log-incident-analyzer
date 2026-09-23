"""Prompt construction for incident analysis."""
from datetime import datetime

ALLOWED_CATEGORIES = (
    "timeout",
    "database",
    "auth",
    "network",
    "config",
    "resource",
    "dependency",
    "application",
    "other",
)

SYSTEM_PROMPT = """\
You are a site-reliability engineer analyzing log incidents.
Rules:
- Use ONLY the log lines provided. Do not guess or invent details beyond them.
- Reply with ONLY a JSON object, no markdown, no commentary, matching exactly:
{"title": string, "category": string, "severity": string, "summary": string, "likely_cause": string, "evidence_lines": array of integers}
- "title": short human-readable incident title (max 80 chars).
- "category": one of: timeout, database, auth, network, config, resource (memory/disk/CPU), dependency (external service), application (code error/exception), other.
- "severity": one of: low, medium, high, critical.
- "summary": 1-3 plain-language sentences describing what happened, including time range and volume when evident.
- "likely_cause": the most likely cause, grounded only in the provided lines.
- "evidence_lines": 1-5 line numbers from the provided sample that best support your conclusion.
"""


def _fmt_ts(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_user_prompt(
    service: str,
    level: str,
    event_count: int,
    first_seen: datetime,
    last_seen: datetime,
    sample_events: list[tuple[int, datetime, str, str]],
) -> str:
    """Build the per-incident user prompt.

    ``sample_events`` is a list of (line_number, timestamp, level, message)
    tuples, already truncated to 500 chars each. The whole sample block is
    truncated to 8,000 characters.
    """
    lines = [
        f"{line_number} | {_fmt_ts(ts)} | {lvl} | {message}"
        for line_number, ts, lvl, message in sample_events
    ]
    sample_block = "\n".join(lines)
    if len(sample_block) > 8000:
        sample_block = sample_block[:8000]

    return (
        f"Service: {service}\n"
        f"Highest level: {level}\n"
        f"Event count: {event_count}\n"
        f"First seen: {_fmt_ts(first_seen)}\n"
        f"Last seen: {_fmt_ts(last_seen)}\n"
        f"Sample events ({len(sample_events)} of {event_count}):\n"
        f"{sample_block}"
    )
