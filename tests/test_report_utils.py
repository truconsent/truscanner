from src.report_utils import get_next_report_filename, sanitize_directory_name


def test_sanitize_directory_name_replaces_invalid_characters():
    result = sanitize_directory_name("/tmp/My Project:2026")
    assert result == "My_Project_2026"


def test_get_next_report_filename_increments_suffix(tmp_path):
    assert get_next_report_filename(tmp_path, "txt") == "truscan_report.txt"

    (tmp_path / "truscan_report.txt").write_text("report", encoding="utf-8")
    (tmp_path / "truscan_report3.txt").write_text("report", encoding="utf-8")

    assert get_next_report_filename(tmp_path, "txt") == "truscan_report4.txt"
