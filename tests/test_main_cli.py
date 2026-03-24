import importlib
from pathlib import Path

from click.testing import CliRunner


class DummyRegexScanner:
    def __init__(self, *args, **kwargs):
        self.data_elements = [{"name": "Email Address"}]

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
    def __init__(self, *args, **kwargs):
        pass

    def get_available_ollama_models(self):
        return []


def test_scan_cli_handles_missing_ollama_models_without_crashing(tmp_path, monkeypatch):
    main_module = importlib.reload(importlib.import_module("src.main"))

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(main_module, "select_file_format", lambda: "txt")
    monkeypatch.setattr(main_module, "select_ai_provider", lambda default_provider=None: "ollama")
    monkeypatch.setattr(main_module.click, "prompt", lambda *args, **kwargs: "N")
    monkeypatch.setattr(main_module, "show_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "RegexScanner", DummyRegexScanner)
    monkeypatch.setattr(main_module, "AIScanner", DummyAIScanner)
    monkeypatch.setattr(
        main_module,
        "run_ai_scan",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("AI scan should not run when no Ollama model is available")
        ),
    )

    runner = CliRunner()
    result = runner.invoke(main_module.main, ["scan", str(project_dir)])

    assert result.exit_code == 0, result.output
    assert "No Ollama models found" in result.output
    assert "reports/project/truscan_report.txt" in result.output
    assert (tmp_path / "reports" / "project" / "truscan_report.txt").exists()


def test_main_module_loads_env_from_current_working_directory(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "TRUSCANNER_ACCESS_KEY_ID=test-access-key",
                "TRUSCANNER_SECRET_ACCESS_KEY=test-secret-key",
                "TRUSCANNER_REGION=us-east-1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TRUSCANNER_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("TRUSCANNER_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("TRUSCANNER_REGION", raising=False)

    main_module = importlib.reload(importlib.import_module("src.main"))

    assert main_module.get_missing_provider_requirements("bedrock") == []
