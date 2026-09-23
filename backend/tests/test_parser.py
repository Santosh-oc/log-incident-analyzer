"""Unit tests for the JSONL parser."""
import gzip
import json
from datetime import datetime, timezone

from app.parsing.jsonl_parser import parse_jsonl, parse_timestamp, normalize_level


def _lines(*objs) -> bytes:
    return "\n".join(json.dumps(o) for o in objs).encode() + b"\n"


def test_valid_lines_basic():
    data = _lines(
        {"ts": "2026-09-22T14:03:11Z", "level": "error", "service": "payment-service", "msg": "Timeout calling bank-gateway"},
        {"ts": "2026-09-22T14:03:12Z", "level": "info", "service": "api", "msg": "GET /orders 200 45ms"},
    )
    result = parse_jsonl(data)
    assert result.total_lines == 2
    assert result.parsed_events == 2
    assert result.unparsed_lines == 0
    assert result.unparsed_samples == []
    e0, e1 = result.events
    assert e0.line_number == 1
    assert e0.timestamp == datetime(2026, 9, 22, 14, 3, 11, tzinfo=timezone.utc)
    assert e0.level == "ERROR"
    assert e0.service == "payment-service"
    assert e0.message == "Timeout calling bank-gateway"
    assert e1.level == "INFO"


def test_field_mapping_variants():
    data = _lines(
        {"timestamp": "2026-09-22T14:03:15.210Z", "severity": "ERROR", "app": "api", "message": "DB connection refused"},
        {"time": "2026-09-22T14:03:16Z", "lvl": "warn", "logger": "db", "text": "slow query"},
        {"@timestamp": "2026-09-22T14:03:17Z", "log.level": "fatal", "component": "core", "message": "crash"},
    )
    result = parse_jsonl(data)
    assert result.parsed_events == 3
    e0, e1, e2 = result.events
    assert e0.timestamp == datetime(2026, 9, 22, 14, 3, 15, 210000, tzinfo=timezone.utc)
    assert e0.level == "ERROR"
    assert e0.service == "api"
    assert e1.level == "WARN"
    assert e1.service == "db"
    assert e2.level == "FATAL"
    assert e2.service == "core"


def test_first_key_wins():
    data = _lines({"ts": "2026-09-22T14:03:11Z", "timestamp": "2026-09-22T15:00:00Z", "msg": "hello"})
    result = parse_jsonl(data)
    assert result.events[0].timestamp == datetime(2026, 9, 22, 14, 3, 11, tzinfo=timezone.utc)


def test_epoch_seconds_and_milliseconds():
    data = _lines(
        {"ts": 1758619391, "msg": "epoch seconds"},
        {"ts": 1758619391000, "msg": "epoch millis"},
        {"ts": "1758619391", "msg": "epoch string"},
    )
    result = parse_jsonl(data)
    assert result.parsed_events == 3
    expected = datetime.fromtimestamp(1758619391, tz=timezone.utc)
    for e in result.events:
        assert e.timestamp == expected


def test_naive_timestamp_treated_as_utc():
    data = _lines({"ts": "2026-09-22T14:03:11", "msg": "naive"})
    result = parse_jsonl(data)
    assert result.events[0].timestamp == datetime(2026, 9, 22, 14, 3, 11, tzinfo=timezone.utc)


def test_level_normalization():
    assert normalize_level("warning") == "WARN"
    assert normalize_level("critical") == "FATAL"
    assert normalize_level("crit") == "FATAL"
    assert normalize_level("panic") == "FATAL"
    assert normalize_level("err") == "ERROR"
    assert normalize_level("ERROR") == "ERROR"
    assert normalize_level("bogus") == "INFO"
    assert normalize_level(None) == "INFO"
    assert normalize_level(42) == "INFO"


def test_missing_service_defaults_unknown():
    data = _lines({"ts": "2026-09-22T14:03:11Z", "msg": "no service"})
    result = parse_jsonl(data)
    assert result.events[0].service == "unknown"


def test_invalid_json_is_unparsed():
    data = b"not json at all\n" + _lines({"ts": "2026-09-22T14:03:11Z", "msg": "ok"})
    result = parse_jsonl(data)
    assert result.total_lines == 2
    assert result.parsed_events == 1
    assert result.unparsed_lines == 1
    assert result.unparsed_samples == [1]


def test_non_object_json_is_unparsed():
    data = b"[1, 2, 3]\n" + _lines({"ts": "2026-09-22T14:03:11Z", "msg": "ok"})
    result = parse_jsonl(data)
    assert result.unparsed_lines == 1
    assert result.unparsed_samples == [1]


def test_missing_timestamp_or_message_is_unparsed():
    data = _lines(
        {"level": "error", "msg": "no timestamp"},
        {"ts": "2026-09-22T14:03:11Z"},
        {"ts": "2026-09-22T14:03:12Z", "msg": "ok"},
    )
    result = parse_jsonl(data)
    assert result.parsed_events == 1
    assert result.unparsed_lines == 2
    assert result.unparsed_samples == [1, 2]


def test_blank_lines_skipped_not_counted():
    data = b"\n\n" + _lines({"ts": "2026-09-22T14:03:11Z", "msg": "ok"}) + b"\n\n"
    result = parse_jsonl(data)
    assert result.total_lines == 1
    assert result.parsed_events == 1
    assert result.unparsed_lines == 0


def test_unparsed_samples_capped_at_10():
    data = b"".join(b"bad line\n" for _ in range(15))
    result = parse_jsonl(data)
    assert result.unparsed_lines == 15
    assert result.unparsed_samples == list(range(1, 11))


def test_gzip_input():
    raw = _lines(
        {"ts": "2026-09-22T14:03:11Z", "level": "error", "service": "svc", "msg": "boom"},
    )
    data = gzip.compress(raw)
    result = parse_jsonl(data)
    assert result.parsed_events == 1
    assert result.events[0].message == "boom"


def test_never_crashes_on_mixed_garbage():
    data = (
        b"\x00\x01binary garbage\n"
        + _lines({"ts": "2026-09-22T14:03:11Z", "msg": "fine"})
        + b'{"ts": "not-a-date", "msg": "bad ts"}\n'
    )
    result = parse_jsonl(data)
    assert result.parsed_events == 1
    assert result.unparsed_lines == 2


def test_parse_timestamp_invalid_returns_none():
    assert parse_timestamp("not-a-date") is None
    assert parse_timestamp(None) is None
    assert parse_timestamp("") is None
    assert parse_timestamp(True) is None
