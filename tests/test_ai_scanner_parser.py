"""Tests for src.ai_parser and AIScanner prompt/content preparation."""

import json

import pytest

from src.ai_parser import (
    coerce_line_number,
    extract_json_payload,
    line_number_from_prefix,
    parse_llm_response,
    strip_line_prefix,
)
from src.ai_scanner import AIScanner


# ---------------------------------------------------------------------------
# parse_llm_response — happy paths
# ---------------------------------------------------------------------------

def test_parse_llm_response_accepts_list_with_trailing_commas():
    content = """
Some preface text
[
  {
    "line_number": "12",
    "line_content": "email = 'john@example.com'",
    "matched_text": "john@example.com",
    "element_name": "Email Address",
    "element_category": "Contact Information",
    "reason": "Contains an email address",
  },
]
"""
    findings = parse_llm_response(content, "src/app.py", "qwen2.5:3b")

    assert len(findings) == 1
    assert findings[0]["line_number"] == 12
    assert findings[0]["filename"] == "src/app.py"
    assert findings[0]["source"] == "LLM (qwen2.5:3b)"


def test_parse_llm_response_accepts_object_payload():
    content = """
{
  "findings": [
    {
      "line_number": 4,
      "context": "const ip = '127.0.0.1';",
      "matched": "127.0.0.1",
      "element_name": "IP Address",
      "element_category": "Digital IDs",
      "reason": "Contains an IP"
    }
  ]
}
"""
    findings = parse_llm_response(content, "src/utils.py", "gemma3:4b")

    assert len(findings) == 1
    assert findings[0]["line_content"] == "const ip = '127.0.0.1';"
    assert findings[0]["matched_text"] == "127.0.0.1"
    assert findings[0]["source"] == "LLM (gemma3:4b)"


def test_parse_llm_response_returns_empty_when_no_json():
    findings = parse_llm_response("No findings in this response", "src/main.py", "llama3")
    assert findings == []


def test_parse_llm_response_returns_empty_for_empty_findings_list():
    content = '{"findings": []}'
    findings = parse_llm_response(content, "src/main.py", "llama3")
    assert findings == []


def test_parse_llm_response_strips_markdown_code_fence():
    content = '```json\n{"findings": [{"line_number": 1, "element_name": "Phone", "element_category": "Contact", "matched_text": "555-1234", "line_content": "phone = 555-1234", "reason": ""}]}\n```'
    findings = parse_llm_response(content, "app.py", "gpt-4o")
    assert len(findings) == 1
    assert findings[0]["element_name"] == "Phone"


def test_parse_llm_response_drops_findings_missing_element_name():
    content = json.dumps({
        "findings": [
            {"line_number": 1, "element_name": "", "element_category": "PII", "matched_text": "foo", "line_content": "x"},
            {"line_number": 2, "element_name": "Email", "element_category": "Contact", "matched_text": "a@b.com", "line_content": "email = a@b.com"},
        ]
    })
    findings = parse_llm_response(content, "app.py", "llama3")
    assert len(findings) == 1
    assert findings[0]["element_name"] == "Email"


def test_parse_llm_response_resolves_line_content_from_file_lines():
    file_lines = [
        "import os",
        "email = 'user@example.com'",
        "print(email)",
    ]
    content = json.dumps({
        "findings": [{"line_number": 2, "element_name": "Email", "element_category": "Contact", "matched_text": "user@example.com", "line_content": "", "reason": ""}]
    })
    findings = parse_llm_response(content, "app.py", "llama3", file_lines=file_lines)
    assert findings[0]["line_content"] == "email = 'user@example.com'"


def test_parse_llm_response_fallback_line_lookup_by_content():
    file_lines = ["x = 1", "ssn = '123-45-6789'", "y = 2"]
    content = json.dumps({
        "findings": [{"line_number": 0, "element_name": "SSN", "element_category": "PII", "matched_text": "123-45-6789", "line_content": "ssn = '123-45-6789'", "reason": ""}]
    })
    findings = parse_llm_response(content, "app.py", "llama3", file_lines=file_lines)
    assert findings[0]["line_number"] == 2


def test_parse_llm_response_handles_single_finding_object_shorthand():
    """When the whole response is a single finding dict (not wrapped in findings[])."""
    content = json.dumps({
        "line_number": 5,
        "element_name": "Password",
        "element_category": "Auth",
        "matched_text": "hunter2",
        "line_content": "pw = 'hunter2'",
        "reason": "",
    })
    findings = parse_llm_response(content, "auth.py", "mistral")
    assert len(findings) == 1
    assert findings[0]["element_name"] == "Password"


# ---------------------------------------------------------------------------
# extract_json_payload
# ---------------------------------------------------------------------------

def test_extract_json_payload_plain_json():
    assert extract_json_payload('{"findings": []}') == {"findings": []}


def test_extract_json_payload_with_leading_prose():
    payload = extract_json_payload('Here are results:\n{"findings": []}')
    assert payload == {"findings": []}


def test_extract_json_payload_trailing_comma():
    result = extract_json_payload('{"items": [1, 2,]}')
    assert result == {"items": [1, 2]}


def test_extract_json_payload_empty_returns_none():
    assert extract_json_payload("") is None
    assert extract_json_payload("   ") is None


def test_extract_json_payload_garbage_returns_none():
    assert extract_json_payload("not json at all!!!") is None


def test_extract_json_payload_list_root():
    result = extract_json_payload('[{"a": 1}]')
    assert result == [{"a": 1}]


# ---------------------------------------------------------------------------
# coerce_line_number
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (5, 5),
    (0, 0),
    (-1, 0),
    (3.7, 3),
    ("42", 42),
    ("L42", 42),
    ("line 7", 7),
    ("bad", 0),
    (None, 0),
])
def test_coerce_line_number(value, expected):
    assert coerce_line_number(value) == expected


# ---------------------------------------------------------------------------
# line_number_from_prefix / strip_line_prefix
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("L12: some code", 12),
    ("42: some code", 42),
    ("L5 - code", 5),
    ("no prefix here", 0),
    ("", 0),
])
def test_line_number_from_prefix(text, expected):
    assert line_number_from_prefix(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("L12: some code", "some code"),
    ("42: some code", "some code"),
    ("plain line", "plain line"),
    ("", ""),
])
def test_strip_line_prefix(text, expected):
    assert strip_line_prefix(text) == expected


# ---------------------------------------------------------------------------
# AIScanner — prompt and content preparation
# ---------------------------------------------------------------------------

def test_prompt_uses_only_filename_not_full_path(tmp_path):
    scanner = AIScanner(data_elements_dir=tmp_path)
    prompt = scanner._get_prompt("code", "/absolute/path/to/secret/app.py")
    assert "/absolute/path/to/secret/" not in prompt
    assert "app.py" in prompt


def test_prompt_includes_all_data_element_names(tmp_path):
    sources = [
        {"name": f"Element {idx}", "category": "Test", "patterns": [f"pattern_{idx}"]}
        for idx in range(30)
    ]
    (tmp_path / "elements.json").write_text(
        json.dumps({"sources": sources}), encoding="utf-8"
    )

    scanner = AIScanner(data_elements_dir=tmp_path)
    prompt = scanner._get_prompt("const value = 1;", "src/example.py")

    marker = "Use these data element types as guidance: "
    assert marker in prompt
    guidance = prompt.split(marker, 1)[1].split("\n\n", 1)[0]
    assert all(f"Element {idx}" in guidance for idx in range(30))


def test_prepare_content_short_file_returned_unchanged(tmp_path):
    scanner = AIScanner(data_elements_dir=tmp_path)
    code = "email = 'a@b.com'\n"
    result = scanner._prepare_content_for_prompt(code)
    assert result == code


def test_prepare_content_large_file_with_signal_is_condensed(tmp_path):
    scanner = AIScanner(data_elements_dir=tmp_path, ai_mode="balanced")
    filler = "x = 1\n" * 500
    signal = "email = 'user@example.com'\n"
    content = filler + signal + filler
    result = scanner._prepare_content_for_prompt(content)
    # Should be shorter than original
    assert len(result) < len(content)
    # Should contain the signal line
    assert "user@example.com" in result


def test_prepare_content_fast_mode_skips_low_signal_large_file(tmp_path):
    scanner = AIScanner(data_elements_dir=tmp_path, ai_mode="fast")
    # No signal keywords/patterns — file should be skipped
    content = ("x = 1\n" * 1000)
    result = scanner._prepare_content_for_prompt(content)
    assert result == "" or len(result) < len(content)


def test_ai_mode_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUSCANNER_AI_MODE", "full")
    scanner = AIScanner(data_elements_dir=tmp_path)
    assert scanner.ai_mode == "full"


def test_ai_mode_invalid_falls_back_to_balanced(tmp_path):
    scanner = AIScanner(data_elements_dir=tmp_path, ai_mode="turbo")
    assert scanner.ai_mode == "balanced"


def test_ai_scanner_scan_file_empty_file_returns_empty(tmp_path):
    empty_file = tmp_path / "empty.py"
    empty_file.write_text("", encoding="utf-8")
    scanner = AIScanner(data_elements_dir=tmp_path)
    results = scanner.scan_file(str(empty_file))
    assert results == []


def test_ai_scanner_scan_file_missing_file_returns_empty(tmp_path):
    scanner = AIScanner(data_elements_dir=tmp_path)
    results = scanner.scan_file(str(tmp_path / "nonexistent.py"))
    assert results == []
