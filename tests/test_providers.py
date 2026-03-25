"""Tests for src.providers — base utilities and provider call wrappers."""

import threading
import time

import pytest

from src.providers.base import extract_message_content, run_with_progress


# ---------------------------------------------------------------------------
# run_with_progress
# ---------------------------------------------------------------------------

def test_run_with_progress_returns_fn_result(capsys):
    result = run_with_progress("fake/file.py", lambda: 42)
    assert result == 42


def test_run_with_progress_reraises_exception(capsys):
    def boom():
        raise ValueError("provider failed")

    with pytest.raises(ValueError, match="provider failed"):
        run_with_progress("fake/file.py", boom)


def test_run_with_progress_prints_completion_line(capsys):
    run_with_progress("myfile.py", lambda: None)
    captured = capsys.readouterr()
    assert "myfile.py" in captured.out


def test_run_with_progress_slow_fn_shows_spinner(capsys):
    def slow():
        time.sleep(0.25)
        return "done"

    result = run_with_progress("slow.py", slow)
    assert result == "done"
    captured = capsys.readouterr()
    assert "slow.py" in captured.out


# ---------------------------------------------------------------------------
# extract_message_content
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("response,expected", [
    # dict-style (ollama older API)
    ({"message": {"content": "hello"}}, "hello"),
    # nested None content
    ({"message": {"content": None}}, ""),
    # attr-style (ollama newer API)
    (type("R", (), {"message": type("M", (), {"content": "world"})()})(), "world"),
    # empty dict
    ({}, ""),
    # non-dict, non-attr
    ("raw string", ""),
])
def test_extract_message_content(response, expected):
    assert extract_message_content(response) == expected


def test_extract_message_content_dict_message_as_dict():
    response = {"message": {"content": "found email"}}
    assert extract_message_content(response) == "found email"


def test_extract_message_content_attr_message_dict():
    class Msg:
        pass
    msg = Msg()
    msg.content = "attr content"

    class Response:
        message = msg

    assert extract_message_content(Response()) == "attr content"
