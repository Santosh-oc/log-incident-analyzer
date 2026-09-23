"""Validation of LLM analysis responses."""
import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.llm.prompt import ALLOWED_CATEGORIES

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class AnalysisResult(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: Literal[
        "timeout", "database", "auth", "network", "config",
        "resource", "dependency", "application", "other",
    ]
    severity: Literal["low", "medium", "high", "critical"]
    summary: str = Field(min_length=1)
    likely_cause: str = Field(min_length=1)
    evidence_lines: list[int] = Field(default_factory=list)


class ValidationError_(Exception):
    """Raised when an LLM response cannot be parsed/validated."""

    def __init__(self, message: str, raw_snippet: str = "") -> None:
        super().__init__(message)
        self.raw_snippet = raw_snippet


def _strip_think(text: str) -> str:
    return _THINK_RE.sub("", text)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (possibly with language tag) and closing fence.
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def extract_json_object(text: str) -> str:
    """Return the substring of the first balanced top-level JSON object."""
    start = text.find("{")
    if start == -1:
        raise ValidationError_("No JSON object found in LLM response.")
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValidationError_("Unbalanced JSON object in LLM response.")


def validate_response(raw: str, allowed_evidence_lines: set[int]) -> AnalysisResult:
    """Parse and validate a raw LLM response.

    Raises ValidationError_ with a readable message on failure.
    """
    cleaned = _strip_fences(_strip_think(raw))
    try:
        json_text = extract_json_object(cleaned)
        data = json.loads(json_text)
    except ValidationError_ as exc:
        raise ValidationError_(str(exc), _snippet(raw)) from None
    except json.JSONDecodeError as exc:
        raise ValidationError_(f"LLM response is not valid JSON: {exc.msg}", _snippet(raw)) from None

    try:
        result = AnalysisResult.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        raise ValidationError_(f"LLM response failed validation: {problems}", _snippet(raw)) from None

    # Keep only evidence lines that were actually sent to the model.
    result.evidence_lines = [ln for ln in result.evidence_lines if ln in allowed_evidence_lines]
    return result


def _snippet(raw: str) -> str:
    raw = raw.strip()
    return raw[:300] + ("…" if len(raw) > 300 else "")
