"""Group WARN/ERROR/FATAL events into incidents.

Pure logic — no database or LLM imports, so this module is easy to unit-test.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.parsing.fingerprint import fingerprint

GROUPED_LEVELS = ("WARN", "ERROR", "FATAL")
_LEVEL_RANK = {"WARN": 0, "ERROR": 1, "FATAL": 2}


@dataclass
class IncidentGroup:
    id: uuid.UUID
    service: str
    level: str
    fingerprint: str
    sample_message: str
    event_count: int
    first_seen: datetime
    last_seen: datetime
    event_ids: list[int]


def group_events(events, gap_minutes: int = 5) -> list[IncidentGroup]:
    """Group events into incidents.

    ``events`` is an iterable of objects with attributes: id, service, level,
    message, timestamp. Only WARN/ERROR/FATAL events are grouped. Events with
    the same service and fingerprint belong to the same incident while the gap
    between consecutive events is <= gap_minutes; a larger gap starts a new
    incident.
    """
    gap = timedelta(minutes=gap_minutes)
    candidates = [e for e in events if e.level in GROUPED_LEVELS]
    candidates.sort(key=lambda e: e.timestamp)

    groups: list[IncidentGroup] = []
    open_by_key: dict[tuple[str, str], IncidentGroup] = {}

    for event in candidates:
        fp = fingerprint(event.message)
        key = (event.service, fp)
        group = open_by_key.get(key)
        if group is not None and event.timestamp - group.last_seen > gap:
            # Gap exceeded: close this group, start a new one.
            del open_by_key[key]
            group = None
        if group is None:
            group = IncidentGroup(
                id=uuid.uuid4(),
                service=event.service,
                level=event.level,
                fingerprint=fp,
                sample_message=event.message,
                event_count=0,
                first_seen=event.timestamp,
                last_seen=event.timestamp,
                event_ids=[],
            )
            groups.append(group)
            open_by_key[key] = group
        group.event_count += 1
        group.last_seen = event.timestamp
        if _LEVEL_RANK[event.level] > _LEVEL_RANK[group.level]:
            group.level = event.level
        group.event_ids.append(event.id)

    return groups
