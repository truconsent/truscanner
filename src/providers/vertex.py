"""Google Vertex AI provider for AI-based privacy scanning.

Uses Vertex AI's OpenAI-compatible endpoint (the ``openai`` package is already
a dependency for the OpenAI provider) so no separate Vertex SDK is required.
Authentication uses Application Default Credentials (ADC) — on Cloud Run,
Cloud Functions, or GCE this is the runtime service account's own identity,
no static key needed.
"""

from typing import Any, Optional

from openai import OpenAI

from .base import run_with_progress


def _get_access_token() -> str:
    import google.auth
    import google.auth.transport.requests

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token  # type: ignore[return-value]


def call_vertex(
    prompt: str,
    filepath: str,
    *,
    project_id: str,
    location: str,
    model: str,
    access_token: Optional[str] = None,
) -> str:
    """Send *prompt* to a Vertex AI model via its OpenAI-compatible endpoint.

    Args:
        prompt: The full prompt string to send to the model.
        filepath: Path of the file being scanned (used only for progress display).
        project_id: GCP project ID hosting the Vertex AI endpoint.
        location: Vertex AI region, e.g. ``"asia-south1"``.
        model: Vertex AI model ID, e.g. ``"google/gemini-2.5-flash"``.
        access_token: Pre-fetched OAuth2 access token. When omitted, one is
            obtained from Application Default Credentials.

    Returns:
        Raw text from the model response, or an empty string on failure.
    """
    def _call() -> Any:
        token = access_token or _get_access_token()
        base_url = (
            f"https://{location}-aiplatform.googleapis.com/v1beta1/"
            f"projects/{project_id}/locations/{location}/endpoints/openapi"
        )
        client = OpenAI(base_url=base_url, api_key=token)
        # The OpenAI-compatible endpoint expects the vendor-qualified model id
        # (e.g. "google/gemini-2.5-flash") — do not strip the "google/" prefix.
        return client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )

    response = run_with_progress(filepath, _call)
    if not response:
        return ""
    return response.choices[0].message.content or ""
