#!/usr/bin/env python3
"""Smoke test for the public Python API: `import truscanner; truscanner(path)`."""

import json
import sys
import tempfile
from pathlib import Path

import truscanner


def _build_demo_project() -> Path:
    temp_root = Path(tempfile.mkdtemp(prefix="truscanner-smoke-"))
    project_dir = temp_root / "demo_project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "app.py").write_text(
        "email = 'demo@example.com'\n"
        "phone = '+1 555 111 2233'\n",
        encoding="utf-8",
    )
    return project_dir


def _run_scan(path: Path):
    print(f"Scanning local path: {path}")
    path_result = truscanner(str(path))

    print(f"Scanning file URL: {path.as_uri()}")
    url_result = truscanner(path.as_uri())

    required_keys = {
        "scan_report_id",
        "directory_scanned",
        "total_findings",
        "scan_duration_seconds",
        "findings",
        "ai_enabled",
        "ai_model",
        "ai_total_findings",
        "ai_scan_duration_seconds",
        "ai_findings",
    }

    missing_path = required_keys - set(path_result)
    missing_url = required_keys - set(url_result)

    if missing_path or missing_url:
        raise RuntimeError(
            f"Missing keys. path_missing={sorted(missing_path)}, "
            f"url_missing={sorted(missing_url)}"
        )

    summary = {
        "path_total_findings": path_result["total_findings"],
        "url_total_findings": url_result["total_findings"],
        "path_report_id": path_result["scan_report_id"],
        "url_report_id": url_result["scan_report_id"],
    }
    print("Smoke test passed. Summary:")
    print(json.dumps(summary, indent=2))


def main():
    if len(sys.argv) > 1:
        target = Path(sys.argv[1]).expanduser().resolve()
        if not target.exists():
            raise FileNotFoundError(f"Target path does not exist: {target}")
    else:
        target = _build_demo_project()
        print(f"No path provided. Using demo project: {target}")

    _run_scan(target)


if __name__ == "__main__":
    main()

