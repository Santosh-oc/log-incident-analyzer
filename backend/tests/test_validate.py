"""Unit tests for LLM response validation."""
import json

import pytest

from app.llm.validate import ValidationError_, validate_response

ALLOWED = {1042, 1043, 1188}

GOOD = {
    "title": "Bank gateway timeouts in payment-service",
    "category": "timeout",
    "severity": "high",
    "summary": "Between 14:03 and 14:11, 214 payment requests timed out.",
    "likely_cause": "bank-gateway is unresponsive or overloaded.",
    "evidence_lines": [1042, 1043, 1188],
}


def test_clean_json():
    result = validate_response(json.dumps(GOOD), ALLOWED)
    assert result.title == GOOD["title"]
    assert result.category == "timeout"
    assert result.severity == "high"
    assert result.evidence_lines == [1042, 1043, 1188]


def test_markdown_fenced_json():
    raw = "```json\n" + json.dumps(GOOD) + "\n```"
    result = validate_response(raw, ALLOWED)
    assert result.category == "timeout"


def test_think_block_stripped():
    raw = "<think>\nThe user wants an analysis. Let me think...\n</think>\n" + json.dumps(GOOD)
    result = validate_response(raw, ALLOWED)
    assert result.title == GOOD["title"]


def test_json_embedded_in_prose():
    raw = "Here is the analysis:\n" + json.dumps(GOOD) + "\nHope that helps!"
    result = validate_response(raw, ALLOWED)
    assert result.category == "timeout"


def test_bad_category_rejected():
    bad = dict(GOOD, category="performance")
    with pytest.raises(ValidationError_) as exc:
        validate_response(json.dumps(bad), ALLOWED)
    assert "category" in str(exc.value)


def test_bad_severity_rejected():
    bad = dict(GOOD, severity="extreme")
    with pytest.raises(ValidationError_):
        validate_response(json.dumps(bad), ALLOWED)


def test_missing_field_rejected():
    bad = dict(GOOD)
    del bad["summary"]
    with pytest.raises(ValidationError_):
        validate_response(json.dumps(bad), ALLOWED)


def test_invalid_evidence_lines_dropped():
    bad = dict(GOOD, evidence_lines=[1042, 9999, 1188, 424242])
    result = validate_response(json.dumps(bad), ALLOWED)
    assert result.evidence_lines == [1042, 1188]


def test_non_json_rejected_with_snippet():
    with pytest.raises(ValidationError_) as exc:
        validate_response("I cannot produce JSON, sorry.", ALLOWED)
    assert "No JSON object" in str(exc.value)
    assert exc.value.raw_snippet


def test_invalid_json_rejected():
    with pytest.raises(ValidationError_):
        validate_response('{"title": "x",', ALLOWED)


def test_snippet_truncated_to_300():
    long_raw = "x" * 1000
    with pytest.raises(ValidationError_) as exc:
        validate_response(long_raw, ALLOWED)
    assert len(exc.value.raw_snippet) <= 301  # 300 + ellipsis
