import importlib
from pathlib import Path

from click.testing import CliRunner

class DummyRegexScanner:
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
        return "dummy report"

    def generate_markdown_report(self, findings, **kwargs):
        return "# dummy report"

    def generate_json_report(self, findings, **kwargs):
        return {"total_findings": len(findings), "findings": findings}


class DummyAIScanner:
    def get_available_ollama_models(self):
        return []

    def scan_directory(self, directory, use_openai=False, model=None):
        raise AssertionError("AI scan should not run when no model is available")


def test_scan_cli_handles_missing_ai_models_without_crashing(tmp_path, monkeypatch):
    main_module = importlib.reload(importlib.import_module("src.main"))

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    prompts = iter(["Y", "N"])

    monkeypatch.setattr(main_module, "select_file_format", lambda: "txt")
    monkeypatch.setattr(main_module.click, "prompt", lambda *args, **kwargs: next(prompts))
    monkeypatch.setattr(main_module, "show_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "RegexScanner", DummyRegexScanner)
    monkeypatch.setattr(main_module, "AIScanner", DummyAIScanner)

    runner = CliRunner()
    result = runner.invoke(main_module.main, ["scan", str(project_dir)])

    assert result.exit_code == 0, result.output
    assert "No Ollama models found" in result.output
    assert "No additional data elements found by AI." in result.output
    assert (tmp_path / "reports" / "project" / "truscan_report.txt").exists()
