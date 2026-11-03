"""Tests for anthropic/openai-compatible/bedrock provider changes (no network)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src import ai_scanner as ai_mod
from src.providers import anthropic as anth
from src.providers import openai as oai
from src.utils import (
    get_ai_provider_setup_help,
    get_missing_provider_requirements,
    has_bedrock_credentials,
    normalize_ai_provider,
    resolve_default_ai_provider,
)
from truscanner import api

ENV_VARS = [
    "OPENAI_KEY", "TRUSCANNER_OPENAI_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL",
    "TRUSCANNER_OPENAI_BASE_URL", "TRUSCANNER_OPENAI_MODEL",
    "ANTHROPIC_API_KEY", "TRUSCANNER_ANTHROPIC_KEY", "TRUSCANNER_ANTHROPIC_MODEL",
    "TRUSCANNER_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID", "TRUSCANNER_SECRET_ACCESS_KEY",
    "AWS_SECRET_ACCESS_KEY", "TRUSCANNER_SESSION_TOKEN", "AWS_SESSION_TOKEN",
    "TRUSCANNER_PROFILE", "AWS_PROFILE", "TRUSCANNER_REGION", "AWS_REGION",
    "AWS_DEFAULT_REGION", "TRUSCANNER_BEDROCK_USE_DEFAULT_CHAIN",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for v in ENV_VARS:
        monkeypatch.delenv(v, raising=False)


def test_normalize_anthropic():
    assert normalize_ai_provider("Anthropic") == "anthropic"
    assert normalize_ai_provider("claude") == "anthropic"
    assert normalize_ai_provider("bedrock") == "bedrock"


def test_anthropic_requirements_and_default(monkeypatch):
    assert get_missing_provider_requirements("anthropic") == ["ANTHROPIC_API_KEY"]
    assert get_ai_provider_setup_help("anthropic")
    monkeypatch.setenv("TRUSCANNER_ANTHROPIC_KEY", "sk-ant-secret-123456")
    assert get_missing_provider_requirements("anthropic") == []
    assert resolve_default_ai_provider() == "anthropic"


def _fake_response(payload, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    return r


def test_anthropic_request_shape_and_text_concat(monkeypatch):
    post = MagicMock(return_value=_fake_response({
        "content": [
            {"type": "text", "text": '{"a":'},
            {"type": "tool_use", "id": "x"},
            {"type": "text", "text": "1}"},
        ]
    }))
    monkeypatch.setattr(anth.requests, "post", post)
    out = anth.call_anthropic("hi", "f.py", api_key="sk-ant-abc", model="claude-haiku-4-5", max_tokens=77)
    assert out == '{"a":1}'
    args, kwargs = post.call_args
    assert args[0] == "https://api.anthropic.com/v1/messages"
    assert kwargs["headers"]["x-api-key"] == "sk-ant-abc"
    assert kwargs["headers"]["anthropic-version"] == "2023-06-01"
    assert kwargs["json"]["model"] == "claude-haiku-4-5"
    assert kwargs["json"]["max_tokens"] == 77
    assert kwargs["json"]["messages"] == [{"role": "user", "content": "hi"}]


def test_anthropic_error_does_not_leak_key(monkeypatch, capsys):
    key = "sk-ant-supersecretkey"
    monkeypatch.setattr(anth.requests, "post", MagicMock(return_value=_fake_response(
        {"error": {"message": f"invalid x-api-key {key}"}}, status=401)))
    with pytest.raises(RuntimeError) as ei:
        anth.call_anthropic("p", "f.py", api_key=key, model="m")
    assert key not in str(ei.value)
    cap = capsys.readouterr()
    assert key not in cap.out + cap.err


class FakeBadRequest(Exception):
    status_code = 400


def _install_fake_openai(monkeypatch, create):
    client = MagicMock()
    client.chat.completions.create = create
    ctor = MagicMock(return_value=client)
    monkeypatch.setattr(oai, "OpenAI", ctor)
    return ctor


def _ok():
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])


def test_openai_base_url_and_json_object(monkeypatch):
    create = MagicMock(return_value=_ok())
    ctor = _install_fake_openai(monkeypatch, create)
    assert oai.call_openai("p", "f", api_key="k", model="m", base_url="http://x/v1") == "{}"
    ctor.assert_called_once_with(api_key="k", base_url="http://x/v1")
    assert create.call_args.kwargs["response_format"] == {"type": "json_object"}


def test_openai_no_base_url_by_default(monkeypatch):
    ctor = _install_fake_openai(monkeypatch, MagicMock(return_value=_ok()))
    oai.call_openai("p", "f", api_key="k", model="m")
    ctor.assert_called_once_with(api_key="k")


def test_openai_fallback_without_response_format(monkeypatch):
    create = MagicMock(side_effect=[FakeBadRequest("no json_object"), _ok()])
    _install_fake_openai(monkeypatch, create)
    assert oai.call_openai("p", "f", api_key="k", model="m") == "{}"
    assert create.call_count == 2
    assert "response_format" in create.call_args_list[0].kwargs
    assert "response_format" not in create.call_args_list[1].kwargs


def test_openai_non_4xx_not_retried(monkeypatch):
    class Boom(Exception):
        status_code = 500
    create = MagicMock(side_effect=Boom("x"))
    _install_fake_openai(monkeypatch, create)
    with pytest.raises(Boom):
        oai.call_openai("p", "f", api_key="k", model="m")
    assert create.call_count == 1


def test_resolve_ai_model_openai(monkeypatch):
    assert api._resolve_ai_model("openai") == "gpt-4o"
    monkeypatch.setenv("TRUSCANNER_OPENAI_MODEL", "env-model")
    assert api._resolve_ai_model("openai") == "env-model"
    assert api._resolve_ai_model("openai", model="arg-model") == "arg-model"
    assert api._resolve_ai_model("anthropic") == "claude-haiku-4-5"
    monkeypatch.setenv("TRUSCANNER_ANTHROPIC_MODEL", "claude-x")
    assert api._resolve_ai_model("anthropic") == "claude-x"


def test_ai_scanner_openai_uses_env(monkeypatch):
    monkeypatch.setenv("OPENAI_KEY", "sk-openai-12345678")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://compat/v1")
    monkeypatch.setenv("TRUSCANNER_OPENAI_MODEL", "gem")
    call = MagicMock(return_value="{}")
    monkeypatch.setattr(ai_mod, "call_openai", call)
    scanner = ai_mod.AIScanner()
    scanner._call_provider("openai", "p", "f.py", None)
    assert call.call_args.kwargs["base_url"] == "http://compat/v1"
    assert call.call_args.kwargs["model"] == "gem"
    scanner._call_provider("openai", "p", "f.py", "explicit")
    assert call.call_args.kwargs["model"] == "explicit"


def test_ai_scanner_dispatches_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-12345678")
    call = MagicMock(return_value="{}")
    ollama = MagicMock()
    monkeypatch.setattr(ai_mod, "call_anthropic", call)
    monkeypatch.setattr(ai_mod, "call_ollama", ollama)
    scanner = ai_mod.AIScanner()
    scanner._call_provider("anthropic", "p", "f.py", None)
    assert call.call_args.kwargs["api_key"] == "sk-ant-12345678"
    assert call.call_args.kwargs["model"] == "claude-haiku-4-5"
    ollama.assert_not_called()


def test_run_ai_scan_anthropic_not_ollama(monkeypatch):
    from src import scanner as sc
    scn = MagicMock()
    monkeypatch.setattr(sc, "AIScanner", MagicMock(return_value=scn))
    # no key -> empty, and Ollama never consulted
    assert sc.run_ai_scan(".", ai_provider="anthropic") == []
    scn.get_available_ollama_models.assert_not_called()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-12345678")
    scn.scan_directory.return_value = ["f"]
    assert sc.run_ai_scan(".", ai_provider="anthropic") == ["f"]
    scn.get_available_ollama_models.assert_not_called()


def test_bedrock_default_chain_requirements(monkeypatch):
    assert not has_bedrock_credentials()
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    assert not has_bedrock_credentials()
    assert get_missing_provider_requirements("bedrock")
    monkeypatch.setenv("TRUSCANNER_BEDROCK_USE_DEFAULT_CHAIN", "1")
    assert has_bedrock_credentials()
    assert get_missing_provider_requirements("bedrock") == []


def test_bedrock_lambda_env_keys_and_session_token(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAXXXX")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secretsecret")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "tok-123456789")
    assert has_bedrock_credentials()
    assert get_missing_provider_requirements("bedrock") == []

    from src.providers import bedrock as br
    sess = MagicMock()
    sess.client.return_value.converse.return_value = {
        "output": {"message": {"content": [{"text": "ok"}]}}}
    fake_boto = MagicMock()
    fake_boto.session.Session.return_value = sess
    monkeypatch.setattr(br, "boto3", fake_boto)
    monkeypatch.setattr(br, "_HAS_BOTO3", True)
    scanner = ai_mod.AIScanner()
    monkeypatch.setattr(ai_mod, "call_bedrock", br.call_bedrock)
    assert scanner._call_provider("bedrock", "p", "f.py", None) == "ok"
    kw = fake_boto.session.Session.call_args.kwargs
    assert kw["aws_session_token"] == "tok-123456789"


def test_bedrock_default_chain_session_has_no_static_keys(monkeypatch):
    from src.providers import bedrock as br
    sess = MagicMock()
    sess.client.return_value.converse.return_value = {"output": {"message": {"content": []}}}
    fake_boto = MagicMock()
    fake_boto.session.Session.return_value = sess
    monkeypatch.setattr(br, "boto3", fake_boto)
    monkeypatch.setattr(br, "_HAS_BOTO3", True)
    br.call_bedrock("p", "f", model_id="m", region="us-east-1")
    assert fake_boto.session.Session.call_args.kwargs == {"region_name": "us-east-1"}


def test_scan_errors_do_not_log_key(monkeypatch, tmp_path, capsys):
    from loguru import logger
    key = "sk-openai-topsecret-0001"
    monkeypatch.setenv("OPENAI_KEY", key)
    f = tmp_path / "a.py"
    f.write_text("email = 'a@b.com'\n")

    def boom(*a, **k):
        raise RuntimeError(f"Incorrect API key provided: {key}")

    monkeypatch.setattr(ai_mod, "call_openai", boom)
    messages = []
    sink = logger.add(lambda m: messages.append(str(m)), level="DEBUG")
    try:
        ai_mod.AIScanner().scan_file(str(f), provider="openai")
    finally:
        logger.remove(sink)
    cap = capsys.readouterr()
    assert key not in "".join(messages) + cap.out + cap.err
    assert messages  # error was logged, redacted
