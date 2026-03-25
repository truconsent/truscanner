"""Tests for src.utils — credentials, env loading, backend constant."""

import pytest

from src.utils import (
    BACKEND_URL,
    get_bedrock_region,
    get_missing_provider_requirements,
    get_openai_api_key,
    has_bedrock_credentials,
    has_openai_credentials,
    normalize_ai_provider,
    resolve_default_ai_provider,
)


# ---------------------------------------------------------------------------
# BACKEND_URL
# ---------------------------------------------------------------------------

def test_backend_url_is_defined():
    assert BACKEND_URL
    assert BACKEND_URL.startswith("https://")


# ---------------------------------------------------------------------------
# normalize_ai_provider
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("ollama", "ollama"),
    ("Ollama", "ollama"),
    ("openai", "openai"),
    ("OpenAI", "openai"),
    ("bedrock", "bedrock"),
    ("aws_bedrock", "bedrock"),
    ("AWS Bedrock", "bedrock"),
    ("skip", None),
    ("none", None),
    ("Skip AI Scan", None),
    (None, None),
])
def test_normalize_ai_provider(raw, expected):
    assert normalize_ai_provider(raw) == expected


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------

def test_get_openai_api_key_reads_env(monkeypatch):
    monkeypatch.setenv("OPENAI_KEY", "sk-test")
    monkeypatch.delenv("TRUSCANNER_OPENAI_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert get_openai_api_key() == "sk-test"


def test_get_openai_api_key_fallback_order(monkeypatch):
    monkeypatch.delenv("OPENAI_KEY", raising=False)
    monkeypatch.setenv("TRUSCANNER_OPENAI_KEY", "sk-truscanner")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert get_openai_api_key() == "sk-truscanner"


def test_get_openai_api_key_none_when_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_KEY", raising=False)
    monkeypatch.delenv("TRUSCANNER_OPENAI_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert get_openai_api_key() is None


def test_has_openai_credentials_true(monkeypatch):
    monkeypatch.setenv("OPENAI_KEY", "sk-test")
    assert has_openai_credentials() is True


def test_has_openai_credentials_false(monkeypatch):
    monkeypatch.delenv("OPENAI_KEY", raising=False)
    monkeypatch.delenv("TRUSCANNER_OPENAI_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert has_openai_credentials() is False


def test_has_bedrock_credentials_with_static_keys(monkeypatch):
    monkeypatch.setenv("TRUSCANNER_ACCESS_KEY_ID", "AK")
    monkeypatch.setenv("TRUSCANNER_SECRET_ACCESS_KEY", "SK")
    monkeypatch.setenv("TRUSCANNER_REGION", "us-east-1")
    monkeypatch.delenv("TRUSCANNER_PROFILE", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    assert has_bedrock_credentials() is True


def test_has_bedrock_credentials_false_when_no_region(monkeypatch):
    monkeypatch.setenv("TRUSCANNER_ACCESS_KEY_ID", "AK")
    monkeypatch.setenv("TRUSCANNER_SECRET_ACCESS_KEY", "SK")
    monkeypatch.delenv("TRUSCANNER_REGION", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    assert has_bedrock_credentials() is False


def test_has_bedrock_credentials_with_profile(monkeypatch):
    monkeypatch.setenv("TRUSCANNER_PROFILE", "myprofile")
    monkeypatch.setenv("TRUSCANNER_REGION", "eu-west-1")
    monkeypatch.delenv("TRUSCANNER_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    assert has_bedrock_credentials() is True


# ---------------------------------------------------------------------------
# get_missing_provider_requirements
# ---------------------------------------------------------------------------

def test_missing_requirements_openai_when_no_key(monkeypatch):
    monkeypatch.delenv("OPENAI_KEY", raising=False)
    monkeypatch.delenv("TRUSCANNER_OPENAI_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    missing = get_missing_provider_requirements("openai")
    assert "OPENAI_KEY" in missing


def test_missing_requirements_openai_when_key_present(monkeypatch):
    monkeypatch.setenv("OPENAI_KEY", "sk-test")
    assert get_missing_provider_requirements("openai") == []


def test_missing_requirements_bedrock_no_region(monkeypatch):
    monkeypatch.setenv("TRUSCANNER_ACCESS_KEY_ID", "AK")
    monkeypatch.setenv("TRUSCANNER_SECRET_ACCESS_KEY", "SK")
    monkeypatch.delenv("TRUSCANNER_REGION", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    missing = get_missing_provider_requirements("bedrock")
    assert any("REGION" in m for m in missing)


def test_missing_requirements_ollama_always_empty():
    assert get_missing_provider_requirements("ollama") == []


def test_missing_requirements_none_provider_always_empty():
    assert get_missing_provider_requirements(None) == []


# ---------------------------------------------------------------------------
# resolve_default_ai_provider
# ---------------------------------------------------------------------------

def test_resolve_default_prefers_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_KEY", "sk-test")
    assert resolve_default_ai_provider() == "openai"


def test_resolve_default_falls_back_to_ollama(monkeypatch):
    for key in ("OPENAI_KEY", "TRUSCANNER_OPENAI_KEY", "OPENAI_API_KEY",
                "TRUSCANNER_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID",
                "TRUSCANNER_REGION", "AWS_REGION", "AWS_DEFAULT_REGION",
                "TRUSCANNER_PROFILE", "AWS_PROFILE"):
        monkeypatch.delenv(key, raising=False)
    assert resolve_default_ai_provider() == "ollama"
