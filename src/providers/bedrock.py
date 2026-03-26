"""AWS Bedrock provider for AI-based privacy scanning."""

from typing import Any, Dict, Optional

try:
    import boto3
    _HAS_BOTO3 = True
except ImportError:
    boto3 = None  # type: ignore[assignment]
    _HAS_BOTO3 = False

from .base import run_with_progress


def call_bedrock(
    prompt: str,
    filepath: str,
    *,
    model_id: str,
    region: str,
    access_key_id: Optional[str] = None,
    secret_access_key: Optional[str] = None,
    session_token: Optional[str] = None,
    profile_name: Optional[str] = None,
    max_tokens: int = 350,
) -> str:
    """Send *prompt* to AWS Bedrock via the Converse API and return the response text.

    Authentication priority:
    1. Static credentials (``access_key_id`` + ``secret_access_key``), with an
       optional ``session_token`` for temporary credentials.
    2. Named AWS profile (``profile_name``).
    3. Default boto3 credential chain (IAM role, environment, etc.) when neither
       is provided.

    Args:
        prompt: The full prompt string to send to the model.
        filepath: Path of the file being scanned (used only for progress display).
        model_id: Bedrock model ID, e.g.
            ``"anthropic.claude-3-haiku-20240307-v1:0"``.
        region: AWS region name, e.g. ``"us-east-1"``.
        access_key_id: AWS access key ID (optional).
        secret_access_key: AWS secret access key (optional).
        session_token: AWS session token for temporary credentials (optional).
        profile_name: Named AWS profile to use (optional).
        max_tokens: Maximum tokens the model may generate.

    Returns:
        Raw text from the model response, or an empty string on failure.
    """
    def _call() -> Any:
        if not _HAS_BOTO3:
            raise ImportError("boto3 is required for AWS Bedrock. Install it with: pip install boto3")

        session_kwargs: Dict[str, Any] = {"region_name": region}
        if access_key_id and secret_access_key:
            session_kwargs["aws_access_key_id"] = access_key_id
            session_kwargs["aws_secret_access_key"] = secret_access_key
            if session_token:
                session_kwargs["aws_session_token"] = session_token
        elif profile_name:
            session_kwargs["profile_name"] = profile_name

        session = boto3.session.Session(**session_kwargs)
        client = session.client("bedrock-runtime")
        return client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"temperature": 0, "maxTokens": max_tokens},
        )

    response = run_with_progress(filepath, _call)
    if not response:
        return ""

    output = response.get("output", {}) if isinstance(response, dict) else {}
    message = output.get("message", {}) if isinstance(output, dict) else {}
    content_items = message.get("content", []) if isinstance(message, dict) else []
    return "".join(
        item.get("text", "") for item in content_items if isinstance(item, dict)
    )
