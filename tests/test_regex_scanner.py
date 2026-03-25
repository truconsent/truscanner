"""Tests for src.regex_scanner — scanning, false positive detection, reports."""

import json
from pathlib import Path

import pytest

from src.regex_scanner import RegexScanner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def scanner_with_email_pattern(tmp_path):
    """Return a RegexScanner loaded with a single Email Address pattern."""
    data = {
        "sources": [
            {
                "name": "Email Address",
                "category": "Contact Information",
                "patterns": [r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"],
                "tags": {},
            }
        ]
    }
    (tmp_path / "email.json").write_text(json.dumps(data), encoding="utf-8")
    return RegexScanner(data_elements_dir=tmp_path)


# ---------------------------------------------------------------------------
# scan_text — basic matching
# ---------------------------------------------------------------------------

def test_scan_text_finds_email(scanner_with_email_pattern):
    findings = scanner_with_email_pattern.scan_text("email = 'user@example.com'")
    assert len(findings) == 1
    assert findings[0]["element_name"] == "Email Address"
    assert findings[0]["matched_text"] == "user@example.com"


def test_scan_text_returns_empty_for_no_match(scanner_with_email_pattern):
    findings = scanner_with_email_pattern.scan_text("x = 1 + 2")
    assert findings == []


def test_scan_text_returns_empty_for_empty_input(scanner_with_email_pattern):
    assert scanner_with_email_pattern.scan_text("") == []


def test_scan_text_line_number_is_correct(scanner_with_email_pattern):
    code = "import os\nemail = 'user@example.com'\nprint(email)\n"
    findings = scanner_with_email_pattern.scan_text(code)
    assert findings[0]["line_number"] == 2


def test_scan_text_one_finding_per_element_per_line(scanner_with_email_pattern):
    """Two emails on the same line should produce only one finding for that element."""
    line = "a = 'foo@x.com'; b = 'bar@y.com'"
    findings = scanner_with_email_pattern.scan_text(line)
    assert len(findings) == 1


# ---------------------------------------------------------------------------
# False positive detection
# ---------------------------------------------------------------------------

def test_comment_lines_skipped(scanner_with_email_pattern):
    findings = scanner_with_email_pattern.scan_text("// email = 'user@example.com'")
    assert findings == []


def test_hash_comment_lines_skipped(scanner_with_email_pattern):
    findings = scanner_with_email_pattern.scan_text("# email = 'user@example.com'")
    assert findings == []


def test_word_email_without_at_sign_is_false_positive(scanner_with_email_pattern):
    """The word 'email' alone (no @) should be filtered as a false positive."""
    findings = scanner_with_email_pattern.scan_text("const email = null;")
    # No actual email address → should be empty or filtered
    # The pattern requires @, so this naturally returns no findings
    assert findings == []


def test_return_statement_variable_is_false_positive(scanner_with_email_pattern):
    data = {
        "sources": [
            {
                "name": "Phone Number",
                "category": "Contact Information",
                "patterns": [r"\bphone\b"],
                "tags": {},
            }
        ]
    }
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "phone.json").write_text(json.dumps(data), encoding="utf-8")
        scanner = RegexScanner(data_elements_dir=d)
        findings = scanner.scan_text("return phone;")
        assert findings == []


# ---------------------------------------------------------------------------
# scan_file
# ---------------------------------------------------------------------------

def test_scan_file_returns_findings_with_filename(scanner_with_email_pattern, tmp_path):
    f = tmp_path / "app.py"
    f.write_text("email = 'admin@example.com'\n", encoding="utf-8")
    findings = scanner_with_email_pattern.scan_file(str(f))
    assert len(findings) == 1
    assert findings[0]["filename"] == str(f)


def test_scan_file_missing_file_returns_empty(scanner_with_email_pattern, tmp_path):
    findings = scanner_with_email_pattern.scan_file(str(tmp_path / "ghost.py"))
    assert findings == []


def test_scan_file_binary_looking_content_does_not_raise(scanner_with_email_pattern, tmp_path):
    f = tmp_path / "binary.py"
    f.write_bytes(b"\x00\x01\x02 email@test.com \xff\xfe")
    findings = scanner_with_email_pattern.scan_file(str(f))
    # Should not raise; may or may not find the email depending on encoding
    assert isinstance(findings, list)


# ---------------------------------------------------------------------------
# scan_directory — parallel scanning
# ---------------------------------------------------------------------------

def test_scan_directory_scans_multiple_files(scanner_with_email_pattern, tmp_path):
    (tmp_path / "a.py").write_text("email = 'a@example.com'\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("email = 'b@example.com'\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("x = 1\n", encoding="utf-8")

    findings = scanner_with_email_pattern.scan_directory(str(tmp_path))
    filenames = {f["filename"] for f in findings}
    assert str(tmp_path / "a.py") in filenames
    assert str(tmp_path / "b.py") in filenames


def test_scan_directory_excludes_non_code_files(scanner_with_email_pattern, tmp_path):
    (tmp_path / "app.py").write_text("email = 'a@example.com'\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("email = 'b@example.com'\n", encoding="utf-8")
    (tmp_path / "style.css").write_text(".email { color: red; }\n", encoding="utf-8")

    findings = scanner_with_email_pattern.scan_directory(str(tmp_path))
    scanned = {Path(f["filename"]).name for f in findings}
    assert "notes.txt" not in scanned
    assert "style.css" not in scanned


def test_scan_directory_excludes_node_modules(scanner_with_email_pattern, tmp_path):
    (tmp_path / "app.py").write_text("email = 'a@example.com'\n", encoding="utf-8")
    node_mod = tmp_path / "node_modules" / "pkg"
    node_mod.mkdir(parents=True)
    (node_mod / "index.js").write_text("email = 'b@example.com'\n", encoding="utf-8")

    findings = scanner_with_email_pattern.scan_directory(str(tmp_path))
    scanned = {f["filename"] for f in findings}
    assert not any("node_modules" in p for p in scanned)


def test_scan_directory_path_not_found_returns_empty(scanner_with_email_pattern, tmp_path):
    findings = scanner_with_email_pattern.scan_directory(str(tmp_path / "nonexistent"))
    assert findings == []


def test_scan_directory_single_file_path_works(scanner_with_email_pattern, tmp_path):
    f = tmp_path / "single.py"
    f.write_text("email = 'x@y.com'\n", encoding="utf-8")
    findings = scanner_with_email_pattern.scan_directory(str(f))
    assert len(findings) == 1


def test_scan_directory_progress_callback_called(scanner_with_email_pattern, tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")

    calls = []
    scanner_with_email_pattern.scan_directory(
        str(tmp_path), progress_callback=lambda c, t, f: calls.append((c, t))
    )
    assert len(calls) == 2
    assert calls[-1][0] == 2   # completed == total at the end


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def test_generate_report_no_findings(scanner_with_email_pattern):
    report = scanner_with_email_pattern.generate_report([])
    assert "No data elements found" in report


def test_generate_report_contains_finding(scanner_with_email_pattern, tmp_path):
    findings = [
        {
            "filename": str(tmp_path / "app.py"),
            "line_number": 3,
            "element_name": "Email Address",
            "element_category": "Contact Information",
            "matched_text": "admin@example.com",
            "line_content": "email = 'admin@example.com'",
            "source": "Regex",
            "tags": {},
        }
    ]
    report = scanner_with_email_pattern.generate_report(findings)
    assert "Email Address" in report
    assert "admin@example.com" in report


def test_generate_markdown_report_no_findings(scanner_with_email_pattern):
    report = scanner_with_email_pattern.generate_markdown_report([])
    assert "No data elements found" in report
    assert "# truscanner Report" in report


def test_generate_json_report_structure(scanner_with_email_pattern):
    report = scanner_with_email_pattern.generate_json_report([])
    assert "total_findings" in report
    assert "findings" in report
    assert report["total_findings"] == 0


# ---------------------------------------------------------------------------
# _normalize_extensions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("exts,expected", [
    (["py", ".js", "TS"], {".py", ".js", ".ts"}),
    ([".PY", "GO"], {".py", ".go"}),
    ([], set()),
])
def test_normalize_extensions(exts, expected):
    assert RegexScanner._normalize_extensions(exts) == expected
