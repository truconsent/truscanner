from pathlib import Path

import truscanner
from truscanner.api import scan, scan_ai


def test_truscanner_module_is_callable(monkeypatch):
    expected = {"ok": True}

    monkeypatch.setattr(truscanner, "scan", lambda path_or_url, **kwargs: expected)

    result = truscanner("/tmp/project")

    assert result == expected


def test_scan_accepts_file_url_and_returns_structured_result(tmp_path, monkeypatch):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "app.py").write_text("print('ok')\n", encoding="utf-8")

    captured = {}

    class DummyRegexScanner:
        def __init__(self, *args, **kwargs):
            self.data_elements = [{"name": "Email Address"}]

    def fake_run_regex_scan(directory, extensions=None, regex_scanner=None):
        captured["directory"] = directory
        captured["extensions"] = extensions
        return [
            {
                "filename": str(Path(directory) / "app.py"),
                "line_number": 1,
                "element_name": "Email Address",
                "element_category": "Contact Information",
                "matched_text": "demo@example.com",
                "line_content": "email = 'demo@example.com'",
                "source": "Regex",
            }
        ]

    monkeypatch.setattr("truscanner.api.RegexScanner", DummyRegexScanner)
    monkeypatch.setattr("truscanner.api.run_regex_scan", fake_run_regex_scan)
    monkeypatch.setattr("truscanner.api.generate_report_id", lambda _: "fixed-report-id")

    result = scan(project_dir.as_uri())

    assert result["scan_report_id"] == "fixed-report-id"
    assert result["directory_scanned"] == str(project_dir.resolve())
    assert result["total_findings"] == 1
    assert result["ai_total_findings"] == 0
    assert captured["directory"] == str(project_dir.resolve())
    assert captured["extensions"] is None


def test_scan_with_ai_without_models_does_not_crash(tmp_path, monkeypatch):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "main.py").write_text("print('ok')\n", encoding="utf-8")

    class DummyRegexScanner:
        def __init__(self, *args, **kwargs):
            self.data_elements = []

    class DummyAIScanner:
        DEFAULT_BEDROCK_MODEL = "bedrock-default"
        DEFAULT_OPENAI_MODEL = "gpt-4o"

        def __init__(self, *args, **kwargs):
            pass

        def get_available_ollama_models(self):
            return []

    monkeypatch.setattr("truscanner.api.RegexScanner", DummyRegexScanner)
    monkeypatch.setattr("truscanner.api.AIScanner", DummyAIScanner)
    monkeypatch.setattr("truscanner.api.run_regex_scan", lambda *args, **kwargs: [])
    monkeypatch.setattr("truscanner.api.run_ai_scan", lambda *args, **kwargs: [])
    monkeypatch.setattr("truscanner.api.generate_report_id", lambda _: "fixed-report-id")
    monkeypatch.delenv("OPENAI_KEY", raising=False)
    monkeypatch.delenv("TRUSCANNER_OPENAI_KEY", raising=False)
    monkeypatch.delenv("TRUSCANNER_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("TRUSCANNER_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("TRUSCANNER_REGION", raising=False)
    monkeypatch.delenv("TRUSCANNER_MODEL_ID", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)

    result = scan(str(project_dir), with_ai=True)

    assert result["ai_enabled"] is True
    assert result["ai_provider"] == "ollama"
    assert result["ai_model"] is None
    assert result["ai_total_findings"] == 0
    assert result["ai_findings"] == []


def test_scan_ai_supports_explicit_bedrock_provider(tmp_path, monkeypatch):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "main.py").write_text("print('ok')\n", encoding="utf-8")

    captured = {}

    class DummyAIScanner:
        DEFAULT_BEDROCK_MODEL = "anthropic.claude-3-haiku-20240307-v1:0"
        DEFAULT_OPENAI_MODEL = "gpt-4o"

    def fake_run_ai_scan(directory, ai_provider=None, ai_mode="balanced", model=None, extensions=None, use_openai=False):
        captured["directory"] = directory
        captured["ai_provider"] = ai_provider
        captured["model"] = model
        captured["extensions"] = extensions
        captured["use_openai"] = use_openai
        return []

    monkeypatch.setattr("truscanner.api.AIScanner", DummyAIScanner)
    monkeypatch.setattr("truscanner.api.run_ai_scan", fake_run_ai_scan)
    monkeypatch.setenv("TRUSCANNER_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("TRUSCANNER_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("TRUSCANNER_REGION", "us-east-1")
    monkeypatch.delenv("TRUSCANNER_MODEL_ID", raising=False)

    result = scan_ai(str(project_dir), ai_provider="bedrock")

    assert result["ai_provider"] == "bedrock"
    assert result["ai_model"] == "anthropic.claude-3-haiku-20240307-v1:0"
    assert captured["directory"] == str(project_dir.resolve())
    assert captured["ai_provider"] == "bedrock"
    assert captured["use_openai"] is False


def test_scan_prefers_openai_key_for_provider_detection(tmp_path, monkeypatch):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "main.py").write_text("print('ok')\n", encoding="utf-8")

    captured = {}

    class DummyRegexScanner:
        def __init__(self, *args, **kwargs):
            self.data_elements = []

    def fake_run_ai_scan(directory, ai_provider=None, ai_mode="balanced", model=None, extensions=None, use_openai=False):
        captured["ai_provider"] = ai_provider
        captured["use_openai"] = use_openai
        return []

    monkeypatch.setattr("truscanner.api.RegexScanner", DummyRegexScanner)
    monkeypatch.setattr("truscanner.api.run_regex_scan", lambda *args, **kwargs: [])
    monkeypatch.setattr("truscanner.api.run_ai_scan", fake_run_ai_scan)
    monkeypatch.setattr("truscanner.api.generate_report_id", lambda _: "fixed-report-id")
    monkeypatch.setenv("OPENAI_KEY", "test-openai-key")
    monkeypatch.delenv("TRUSCANNER_OPENAI_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = scan(str(project_dir), with_ai=True)

    assert result["ai_provider"] == "openai"
    assert result["ai_model"] == "gpt-4o"
    assert captured["ai_provider"] == "openai"
    assert captured["use_openai"] is True
