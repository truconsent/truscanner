from pathlib import Path

import src.scanner as scanner_module
from src.ai_scanner import AIScanner
from src.regex_scanner import RegexScanner


def test_regex_scanner_scans_only_code_files_by_default(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "script.JS").write_text("console.log('ok')\n", encoding="utf-8")
    (tmp_path / "native.c").write_text("int main() { return 0; }\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("docs\n", encoding="utf-8")
    (tmp_path / "data.json").write_text("{\"key\": \"value\"}\n", encoding="utf-8")

    scanner = RegexScanner(data_elements_dir=tmp_path, load_immediately=False)
    scanned_files = []

    def fake_scan_file(filepath):
        scanned_files.append(Path(filepath).name)
        return []

    monkeypatch.setattr(scanner, "scan_file", fake_scan_file)
    monkeypatch.setattr(scanner, "_load_data_elements", lambda: None)

    scanner.scan_directory(str(tmp_path))

    assert set(scanned_files) == {"app.py", "script.JS", "native.c"}


def test_ai_scanner_scans_only_code_files_by_default(tmp_path, monkeypatch):
    (tmp_path / "service.py").write_text("print('service')\n", encoding="utf-8")
    (tmp_path / "frontend.tsx").write_text("const x = 1;\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("plain text\n", encoding="utf-8")
    (tmp_path / "schema.json").write_text("{\"a\": 1}\n", encoding="utf-8")

    scanner = AIScanner(data_elements_dir=tmp_path / "empty")
    scanned_files = []

    def fake_scan_file(filepath, use_openai=False, model=None):
        scanned_files.append(Path(filepath).name)
        return []

    monkeypatch.setattr(scanner, "scan_file", fake_scan_file)

    scanner.scan_directory(str(tmp_path), model="qwen2.5:3b")

    assert set(scanned_files) == {"service.py", "frontend.tsx"}


def test_legacy_scanner_module_scans_only_code_files_by_default(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "config.json").write_text("{\"ok\": true}\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("docs\n", encoding="utf-8")

    class DummyRegexScanner:
        DEFAULT_EXCLUDE_DIRS = RegexScanner.DEFAULT_EXCLUDE_DIRS
        DEFAULT_EXCLUDE_FILES = RegexScanner.DEFAULT_EXCLUDE_FILES
        DEFAULT_EXCLUDE_EXTENSIONS = RegexScanner.DEFAULT_EXCLUDE_EXTENSIONS
        DEFAULT_CODE_EXTENSIONS = RegexScanner.DEFAULT_CODE_EXTENSIONS

    scanned_files = []

    def fake_scan_file(filepath, regex_scanner=None):
        scanned_files.append(Path(filepath).name)
        return []

    monkeypatch.setattr(scanner_module, "RegexScanner", DummyRegexScanner)
    monkeypatch.setattr(scanner_module, "scan_file", fake_scan_file)

    scanner_module.scan_directory(str(tmp_path), use_ai=False)

    assert scanned_files == ["main.py"]
