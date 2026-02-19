from pathlib import Path

import truscanner
from truscanner.api import scan


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
        def scan_directory(self, directory, extensions=None):
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

    class DummyAIScanner:
        def get_available_ollama_models(self):
            return []

    monkeypatch.setattr("truscanner.api.RegexScanner", DummyRegexScanner)
    monkeypatch.setattr("truscanner.api.AIScanner", DummyAIScanner)
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
        def scan_directory(self, directory, extensions=None):
            return []

    class DummyAIScanner:
        def get_available_ollama_models(self):
            return []

        def scan_directory(self, directory, use_openai=False, model=None, extensions=None):
            raise AssertionError("AI scan should not run without model or OPENAI key")

    monkeypatch.setattr("truscanner.api.RegexScanner", DummyRegexScanner)
    monkeypatch.setattr("truscanner.api.AIScanner", DummyAIScanner)
    monkeypatch.setattr("truscanner.api.generate_report_id", lambda _: "fixed-report-id")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = scan(str(project_dir), with_ai=True)

    assert result["ai_enabled"] is True
    assert result["ai_total_findings"] == 0
    assert result["ai_findings"] == []
