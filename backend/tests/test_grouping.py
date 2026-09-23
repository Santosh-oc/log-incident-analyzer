"""Unit tests for incident grouping."""
from datetime import datetime, timedelta, timezone

from app.parsing.grouping import group_events


class FakeEvent:
    def __init__(self, id, service, level, message, timestamp):
        self.id = id
        self.service = service
        self.level = level
        self.message = message
        self.timestamp = timestamp


T0 = datetime(2026, 9, 22, 14, 0, 0, tzinfo=timezone.utc)


def _ev(i, service, level, message, minutes=0):
    return FakeEvent(i, service, level, message, T0 + timedelta(minutes=minutes))


def test_only_warn_error_fatal_grouped():
    events = [
        _ev(1, "api", "INFO", "GET / 200"),
        _ev(2, "api", "DEBUG", "cache hit"),
        _ev(3, "api", "ERROR", "boom"),
    ]
    groups = group_events(events, gap_minutes=5)
    assert len(groups) == 1
    assert groups[0].event_count == 1
    assert groups[0].event_ids == [3]


def test_same_fingerprint_within_gap_one_incident():
    events = [
        _ev(1, "api", "ERROR", "Timeout after 30000ms (order_id=A1)"),
        _ev(2, "api", "ERROR", "Timeout after 30000ms (order_id=A2)", minutes=2),
        _ev(3, "api", "ERROR", "Timeout after 30000ms (order_id=A3)", minutes=4),
    ]
    groups = group_events(events, gap_minutes=5)
    assert len(groups) == 1
    assert groups[0].event_count == 3
    assert groups[0].event_ids == [1, 2, 3]
    assert groups[0].first_seen == T0
    assert groups[0].last_seen == T0 + timedelta(minutes=4)


def test_gap_exceeded_starts_new_incident():
    events = [
        _ev(1, "api", "ERROR", "Timeout after 30000ms (order_id=A1)"),
        _ev(2, "api", "ERROR", "Timeout after 30000ms (order_id=A2)", minutes=6),
    ]
    groups = group_events(events, gap_minutes=5)
    assert len(groups) == 2
    assert groups[0].event_ids == [1]
    assert groups[1].event_ids == [2]


def test_gap_exactly_at_limit_stays_together():
    events = [
        _ev(1, "api", "ERROR", "Timeout after 30000ms (order_id=A1)"),
        _ev(2, "api", "ERROR", "Timeout after 30000ms (order_id=A2)", minutes=5),
    ]
    groups = group_events(events, gap_minutes=5)
    assert len(groups) == 1


def test_different_services_separate_incidents():
    events = [
        _ev(1, "api", "ERROR", "Timeout after 30000ms"),
        _ev(2, "db", "ERROR", "Timeout after 30000ms", minutes=1),
    ]
    groups = group_events(events, gap_minutes=5)
    assert len(groups) == 2
    services = {g.service for g in groups}
    assert services == {"api", "db"}


def test_different_fingerprints_separate_incidents():
    events = [
        _ev(1, "api", "ERROR", "Timeout after 30000ms"),
        _ev(2, "api", "ERROR", "DB connection refused", minutes=1),
    ]
    groups = group_events(events, gap_minutes=5)
    assert len(groups) == 2


def test_highest_level_wins():
    events = [
        _ev(1, "api", "WARN", "slow response 1200ms"),
        _ev(2, "api", "ERROR", "slow response 9000ms", minutes=1),
        _ev(3, "api", "WARN", "slow response 1500ms", minutes=2),
    ]
    groups = group_events(events, gap_minutes=5)
    assert len(groups) == 1
    assert groups[0].level == "ERROR"


def test_fatal_is_highest():
    events = [
        _ev(1, "api", "ERROR", "crash 1"),
        _ev(2, "api", "FATAL", "crash 2", minutes=1),
    ]
    groups = group_events(events, gap_minutes=5)
    assert groups[0].level == "FATAL"


def test_unsorted_input_handled():
    events = [
        _ev(3, "api", "ERROR", "Timeout after 30000ms (order_id=A3)", minutes=4),
        _ev(1, "api", "ERROR", "Timeout after 30000ms (order_id=A1)"),
        _ev(2, "api", "ERROR", "Timeout after 30000ms (order_id=A2)", minutes=2),
    ]
    groups = group_events(events, gap_minutes=5)
    assert len(groups) == 1
    assert groups[0].event_ids == [1, 2, 3]


def test_interleaved_services_independent_gaps():
    # api events 10 min apart (new incident), db events 1 min apart (same incident)
    events = [
        _ev(1, "api", "ERROR", "a fail"),
        _ev(2, "db", "ERROR", "d fail", minutes=1),
        _ev(3, "api", "ERROR", "a fail", minutes=10),
        _ev(4, "db", "ERROR", "d fail", minutes=2),
    ]
    groups = group_events(events, gap_minutes=5)
    api_groups = [g for g in groups if g.service == "api"]
    db_groups = [g for g in groups if g.service == "db"]
    assert len(api_groups) == 2
    assert len(db_groups) == 1


def test_empty_input():
    assert group_events([], gap_minutes=5) == []
