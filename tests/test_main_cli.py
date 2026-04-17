"""CLI tests for `truscanner scan`.

All tests go through Click's CliRunner so they exercise the real argument
parsing, option handling, and output formatting — the same surface that
open-source users hit.

Shared helpers
--------------
`_patch_main` sets up the minimal monkeypatching needed to prevent network /
filesystem side-effects (scanner init, AI calls, backend upload) while still
exercising the real CLI logic.

`_make_project` creates a temporary directory with a single Python file so
Click's `exists=True` check on the directory argument passes.
"""

import importlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner


# ---------------------------------------------------------------------------
# Shared stubs
# ---------------------------------------------------------------------------

class DummyRegexScanner:
    """Minimal RegexScanner stub that returns one pre-built finding."""

    def __init__(self, *args, **kwargs):
        self.data_elements = [{"name": "Email Address"}]
        self.last_scan_usage = {
            "files_scanned": 1,
            "input_tokens": 10,
            "output_tokens": 0,
            "total_tokens": 10,
            "tokenizer": "tiktoken",
        }

    def scan_directory(self, directory, progress_callback=None, **kwargs):
        file_path = str(Path(directory) / "app.py")
        if progress_callback:
            progress_callback(1, 1, file_path)
        return [
            {
                "filename": file_path,
                "line_number": 1,
                "element_name": "Email Address",
                "element_category": "Contact Information",
                "matched_text": "demo@example.com",
                "line_content": "email = 'demo@example.com'",
                "source": "Regex",
            }
        ]

    def generate_report(self, findings, **kwargs):
        return f"dummy report ({len(findings)} findings)"

    def generate_markdown_report(self, findings, **kwargs):
        return f"# dummy report ({len(findings)} findings)"

    def generate_json_report(self, findings, **kwargs):
        return {"total_findings": len(findings), "findings": findings}


class DummyRegexScannerNoFindings(DummyRegexScanner):
    """Scanner stub that returns zero findings."""

    def scan_directory(self, directory, progress_callback=None, **kwargs):
        file_path = str(Path(directory) / "app.py")
        if progress_callback:
            progress_callback(1, 1, file_path)
        return []


class DummyAIScanner:
    def __init__(self, *args, **kwargs):
        pass

    def get_available_ollama_models(self):
        return []


class DummyAIScannerWithModels:
    def __init__(self, *args, **kwargs):
        pass

    def get_available_ollama_models(self):
        return ["llama3", "mistral"]


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "app.py").write_text("email = 'demo@example.com'\n", encoding="utf-8")
    return project_dir


def _patch_main(monkeypatch, module, *, file_format="txt", ai_provider=None,
                regex_scanner_cls=DummyRegexScanner, ai_scanner_cls=DummyAIScanner,
                ai_results=None, upload_succeeds=True, upload_answer="N"):
    """Apply standard monkeypatches to isolate the CLI from real I/O."""
    monkeypatch.setattr(module, "select_file_format", lambda: file_format)
    monkeypatch.setattr(module, "select_ai_provider", lambda default_provider=None: ai_provider)
    monkeypatch.setattr(module, "select_ollama_model", lambda models: models[0])
    monkeypatch.setattr(module, "show_progress", lambda *a, **kw: None)
    monkeypatch.setattr(module, "RegexScanner", regex_scanner_cls)
    monkeypatch.setattr(module, "AIScanner", ai_scanner_cls)
    monkeypatch.setattr(module.click, "prompt", lambda *a, **kw: upload_answer)
    monkeypatch.setattr(module, "upload_to_backend", lambda **kw: upload_succeeds)

    effective_ai_results = ai_results if ai_results is not None else []
    monkeypatch.setattr(module, "run_ai_scan", lambda *a, **kw: effective_ai_results)


# ---------------------------------------------------------------------------
# Basic happy path
# ---------------------------------------------------------------------------

def test_scan_exits_zero_on_success(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m)

    result = CliRunner().invoke(m.main, ["scan", str(project_dir)])

    assert result.exit_code == 0, result.output


def test_scan_prints_scanning_message(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m)

    result = CliRunner().invoke(m.main, ["scan", str(project_dir)])

    assert "Scanning:" in result.output


def test_scan_prints_report_id(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m)

    result = CliRunner().invoke(m.main, ["scan", str(project_dir)])

    assert "Scan Report ID:" in result.output


def test_scan_prints_total_findings(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m)

    result = CliRunner().invoke(m.main, ["scan", str(project_dir)])

    assert "Total Findings:" in result.output


def test_scan_prints_time_taken(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m)

    result = CliRunner().invoke(m.main, ["scan", str(project_dir)])

    assert "Time Taken:" in result.output


def test_scan_prints_token_usage(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m)

    result = CliRunner().invoke(m.main, ["scan", str(project_dir)])

    assert "Token Usage:" in result.output


def test_scan_no_findings_still_exits_zero(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m, regex_scanner_cls=DummyRegexScannerNoFindings)

    result = CliRunner().invoke(m.main, ["scan", str(project_dir)])

    assert result.exit_code == 0
    assert "Total Findings: 0" in result.output


def test_scan_nonexistent_directory_exits_nonzero(tmp_path):
    m = importlib.reload(importlib.import_module("src.main"))
    result = CliRunner().invoke(m.main, ["scan", str(tmp_path / "does_not_exist")])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Flags: --version and --help
# ---------------------------------------------------------------------------

def test_version_flag(tmp_path):
    m = importlib.reload(importlib.import_module("src.main"))
    result = CliRunner().invoke(m.main, ["--version"])
    assert result.exit_code == 0
    assert "truscanner" in result.output.lower()


def test_help_flag_shows_scan_command(tmp_path):
    m = importlib.reload(importlib.import_module("src.main"))
    result = CliRunner().invoke(m.main, ["--help"])
    assert result.exit_code == 0
    assert "scan" in result.output


def test_scan_help_shows_options(tmp_path):
    m = importlib.reload(importlib.import_module("src.main"))
    result = CliRunner().invoke(m.main, ["scan", "--help"])
    assert result.exit_code == 0
    for flag in ["--with-ai", "--ai-provider", "--ai-mode", "--personal-only"]:
        assert flag in result.output


# ---------------------------------------------------------------------------
# Report format selection
# ---------------------------------------------------------------------------

def test_txt_format_creates_txt_file(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m, file_format="txt")

    CliRunner().invoke(m.main, ["scan", str(project_dir)])

    assert (tmp_path / "reports" / "project" / "truscan_report.txt").exists()


def test_md_format_creates_md_file(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m, file_format="md")

    CliRunner().invoke(m.main, ["scan", str(project_dir)])

    assert (tmp_path / "reports" / "project" / "truscan_report.md").exists()


def test_json_format_creates_json_file(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m, file_format="json")

    CliRunner().invoke(m.main, ["scan", str(project_dir)])

    json_file = tmp_path / "reports" / "project" / "truscan_report.json"
    assert json_file.exists()
    data = json.loads(json_file.read_text())
    assert "total_findings" in data


def test_all_format_creates_three_files(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m, file_format="all")

    CliRunner().invoke(m.main, ["scan", str(project_dir)])

    reports = tmp_path / "reports" / "project"
    assert (reports / "truscan_report.txt").exists()
    assert (reports / "truscan_report.md").exists()
    assert (reports / "truscan_report.json").exists()


def test_report_path_shown_in_output(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m, file_format="txt")

    result = CliRunner().invoke(m.main, ["scan", str(project_dir)])

    assert "truscan_report.txt" in result.output


def test_second_scan_increments_report_filename(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m, file_format="txt")

    runner = CliRunner()
    runner.invoke(m.main, ["scan", str(project_dir)])
    runner.invoke(m.main, ["scan", str(project_dir)])

    assert (tmp_path / "reports" / "project" / "truscan_report.txt").exists()
    assert (tmp_path / "reports" / "project" / "truscan_report1.txt").exists()


# ---------------------------------------------------------------------------
# AI provider flags
# ---------------------------------------------------------------------------

def test_ai_provider_flag_skips_interactive_prompt(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    # select_ai_provider should NOT be called when --ai-provider is passed
    called = []
    monkeypatch.setattr(m, "select_file_format", lambda: "txt")
    monkeypatch.setattr(m, "select_ai_provider", lambda **kw: called.append(1) or "ollama")
    monkeypatch.setattr(m, "show_progress", lambda *a, **kw: None)
    monkeypatch.setattr(m, "RegexScanner", DummyRegexScanner)
    monkeypatch.setattr(m, "AIScanner", DummyAIScannerWithModels)
    monkeypatch.setattr(m, "select_ollama_model", lambda models: models[0])
    monkeypatch.setattr(m.click, "prompt", lambda *a, **kw: "N")
    monkeypatch.setattr(m, "upload_to_backend", lambda **kw: False)
    monkeypatch.setattr(m, "run_ai_scan", lambda *a, **kw: [])

    CliRunner().invoke(m.main, ["scan", str(project_dir), "--ai-provider", "ollama"])

    assert called == [], "select_ai_provider should not be called when --ai-provider is set"


def test_ai_provider_openai_missing_credentials_shows_error(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m)

    for key in ("OPENAI_KEY", "TRUSCANNER_OPENAI_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    result = CliRunner().invoke(
        m.main, ["scan", str(project_dir), "--ai-provider", "openai"]
    )

    assert result.exit_code == 0
    assert "credentials are not configured" in result.output or "Missing" in result.output


def test_ai_provider_bedrock_missing_credentials_shows_error(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m)

    for key in ("TRUSCANNER_ACCESS_KEY_ID", "TRUSCANNER_SECRET_ACCESS_KEY",
                "TRUSCANNER_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                "AWS_REGION", "AWS_DEFAULT_REGION", "TRUSCANNER_PROFILE", "AWS_PROFILE"):
        monkeypatch.delenv(key, raising=False)

    result = CliRunner().invoke(
        m.main, ["scan", str(project_dir), "--ai-provider", "bedrock"]
    )

    assert result.exit_code == 0
    assert "credentials are not configured" in result.output or "Missing" in result.output


def test_ai_provider_ollama_no_models_shows_error(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m, ai_scanner_cls=DummyAIScanner)  # returns []

    result = CliRunner().invoke(
        m.main, ["scan", str(project_dir), "--ai-provider", "ollama"]
    )

    assert result.exit_code == 0
    assert "No Ollama models found" in result.output


def test_ai_provider_ollama_with_models_runs_ai_scan(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    ai_called = []
    monkeypatch.setattr(m, "select_file_format", lambda: "txt")
    monkeypatch.setattr(m, "select_ai_provider", lambda **kw: None)
    monkeypatch.setattr(m, "select_ollama_model", lambda models: models[0])
    monkeypatch.setattr(m, "show_progress", lambda *a, **kw: None)
    monkeypatch.setattr(m, "RegexScanner", DummyRegexScanner)
    monkeypatch.setattr(m, "AIScanner", DummyAIScannerWithModels)
    monkeypatch.setattr(m.click, "prompt", lambda *a, **kw: "N")
    monkeypatch.setattr(m, "upload_to_backend", lambda **kw: False)
    monkeypatch.setattr(m, "run_ai_scan", lambda *a, **kw: ai_called.append(1) or [])

    CliRunner().invoke(m.main, ["scan", str(project_dir), "--ai-provider", "ollama"])

    assert ai_called, "run_ai_scan should have been called"


def test_ai_provider_openai_with_key_runs_ai_scan(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_KEY", "sk-test")

    ai_called = []
    _patch_main(monkeypatch, m, ai_results=[])
    monkeypatch.setattr(m, "run_ai_scan", lambda *a, **kw: ai_called.append(1) or [])

    CliRunner().invoke(m.main, ["scan", str(project_dir), "--ai-provider", "openai"])

    assert ai_called


def test_ai_provider_bedrock_with_credentials_shows_model_name(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRUSCANNER_ACCESS_KEY_ID", "AK")
    monkeypatch.setenv("TRUSCANNER_SECRET_ACCESS_KEY", "SK")
    monkeypatch.setenv("TRUSCANNER_REGION", "us-east-1")
    _patch_main(monkeypatch, m, ai_results=[])

    result = CliRunner().invoke(
        m.main, ["scan", str(project_dir), "--ai-provider", "bedrock"]
    )

    assert "Bedrock" in result.output or "bedrock" in result.output.lower()


# ---------------------------------------------------------------------------
# AI scan results
# ---------------------------------------------------------------------------

def test_ai_findings_creates_llm_report_file(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_KEY", "sk-test")

    ai_finding = {
        "filename": str(project_dir / "app.py"),
        "line_number": 2,
        "element_name": "SSN",
        "element_category": "PII",
        "matched_text": "123-45-6789",
        "line_content": "ssn = '123-45-6789'",
        "source": "LLM (gpt-4o)",
        "reason": "Contains SSN",
    }
    _patch_main(monkeypatch, m, file_format="txt", ai_results=[ai_finding])

    CliRunner().invoke(m.main, ["scan", str(project_dir), "--ai-provider", "openai"])

    assert (tmp_path / "reports" / "project" / "truscan_report_llm.txt").exists()


def test_ai_no_findings_shows_no_additional_message(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_KEY", "sk-test")
    _patch_main(monkeypatch, m, ai_results=[])

    result = CliRunner().invoke(
        m.main, ["scan", str(project_dir), "--ai-provider", "openai"]
    )

    assert "No additional data elements found by AI" in result.output


def test_ai_findings_count_shown_in_output(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_KEY", "sk-test")

    ai_findings = [
        {"filename": str(project_dir / "app.py"), "line_number": i,
         "element_name": "Email", "element_category": "Contact Information",
         "matched_text": f"user{i}@x.com", "line_content": "", "source": "LLM", "reason": ""}
        for i in range(1, 4)
    ]
    _patch_main(monkeypatch, m, file_format="txt", ai_results=ai_findings)

    result = CliRunner().invoke(
        m.main, ["scan", str(project_dir), "--ai-provider", "openai"]
    )

    assert "Enhanced findings: 3" in result.output


def test_with_ai_flag_sets_ai_default(tmp_path, monkeypatch):
    """--with-ai should pass default_provider=None (not 'skip') to select_ai_provider."""
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    captured = {}
    monkeypatch.setattr(m, "select_file_format", lambda: "txt")
    monkeypatch.setattr(m, "select_ai_provider",
                        lambda default_provider=None: captured.update({"dp": default_provider}) or None)
    monkeypatch.setattr(m, "show_progress", lambda *a, **kw: None)
    monkeypatch.setattr(m, "RegexScanner", DummyRegexScanner)
    monkeypatch.setattr(m, "AIScanner", DummyAIScanner)
    monkeypatch.setattr(m.click, "prompt", lambda *a, **kw: "N")
    monkeypatch.setattr(m, "upload_to_backend", lambda **kw: False)
    monkeypatch.setattr(m, "run_ai_scan", lambda *a, **kw: [])

    CliRunner().invoke(m.main, ["scan", str(project_dir), "--with-ai"])

    assert captured.get("dp") is None  # None means "let user pick", not forced skip


# ---------------------------------------------------------------------------
# AI mode flag
# ---------------------------------------------------------------------------

def test_ai_mode_flag_passed_to_run_ai_scan(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_KEY", "sk-test")

    captured = {}
    monkeypatch.setattr(m, "select_file_format", lambda: "txt")
    monkeypatch.setattr(m, "select_ai_provider", lambda **kw: None)
    monkeypatch.setattr(m, "show_progress", lambda *a, **kw: None)
    monkeypatch.setattr(m, "RegexScanner", DummyRegexScanner)
    monkeypatch.setattr(m, "AIScanner", DummyAIScanner)
    monkeypatch.setattr(m.click, "prompt", lambda *a, **kw: "N")
    monkeypatch.setattr(m, "upload_to_backend", lambda **kw: False)
    monkeypatch.setattr(
        m, "run_ai_scan",
        lambda *a, ai_mode="balanced", **kw: captured.update({"ai_mode": ai_mode}) or []
    )

    CliRunner().invoke(
        m.main, ["scan", str(project_dir), "--ai-provider", "openai", "--ai-mode", "fast"]
    )

    assert captured.get("ai_mode") == "fast"


# ---------------------------------------------------------------------------
# --personal-only flag
# ---------------------------------------------------------------------------

def test_personal_only_filters_non_pii_findings(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    class ScannerWithMixedFindings(DummyRegexScanner):
        def scan_directory(self, directory, progress_callback=None, **kwargs):
            return [
                {"filename": str(Path(directory) / "a.py"), "line_number": 1,
                 "element_name": "Email", "element_category": "Contact Information",
                 "matched_text": "a@b.com", "line_content": "", "source": "Regex", "tags": {}},
                {"filename": str(Path(directory) / "b.py"), "line_number": 2,
                 "element_name": "Device ID", "element_category": "Device Identifiers",
                 "matched_text": "dev-123", "line_content": "", "source": "Regex", "tags": {}},
            ]

    _patch_main(monkeypatch, m, regex_scanner_cls=ScannerWithMixedFindings)

    result = CliRunner().invoke(
        m.main, ["scan", str(project_dir), "--personal-only"]
    )

    # Only the Contact Information finding passes the filter
    assert result.exit_code == 0
    assert "Total Findings: 1" in result.output


# ---------------------------------------------------------------------------
# Upload flow
# ---------------------------------------------------------------------------

def test_upload_prompt_n_does_not_call_upload(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    upload_called = []
    _patch_main(monkeypatch, m, upload_answer="N")
    monkeypatch.setattr(m, "upload_to_backend",
                        lambda **kw: upload_called.append(1) or True)

    CliRunner().invoke(m.main, ["scan", str(project_dir)])

    assert upload_called == []


def test_upload_prompt_y_calls_upload(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    upload_called = []
    _patch_main(monkeypatch, m, upload_answer="Y")
    monkeypatch.setattr(m, "upload_to_backend",
                        lambda **kw: upload_called.append(1) or True)

    CliRunner().invoke(m.main, ["scan", str(project_dir)])

    assert upload_called


def test_upload_success_shows_dashboard_url(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m, upload_answer="Y", upload_succeeds=True)

    result = CliRunner().invoke(m.main, ["scan", str(project_dir)])

    assert "truconsent.io" in result.output


def test_upload_failure_does_not_crash(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m, upload_answer="Y", upload_succeeds=False)

    result = CliRunner().invoke(m.main, ["scan", str(project_dir)])

    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Env loading
# ---------------------------------------------------------------------------

def test_scan_cli_handles_missing_ollama_models_without_crashing(tmp_path, monkeypatch):
    m = importlib.reload(importlib.import_module("src.main"))
    project_dir = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _patch_main(monkeypatch, m, ai_provider="ollama", ai_scanner_cls=DummyAIScanner)

    result = CliRunner().invoke(m.main, ["scan", str(project_dir)])

    assert result.exit_code == 0
    assert "No Ollama models found" in result.output
    assert (tmp_path / "reports" / "project" / "truscan_report.txt").exists()


def test_main_module_loads_env_from_current_working_directory(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TRUSCANNER_ACCESS_KEY_ID=test-access-key\n"
        "TRUSCANNER_SECRET_ACCESS_KEY=test-secret-key\n"
        "TRUSCANNER_REGION=us-east-1\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TRUSCANNER_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("TRUSCANNER_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("TRUSCANNER_REGION", raising=False)

    m = importlib.reload(importlib.import_module("src.main"))

    assert m.get_missing_provider_requirements("bedrock") == []
