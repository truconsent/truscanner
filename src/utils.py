"""Utility functions for interactive menu, progress display, and backend integration."""
import os
import sys
from typing import Optional, Callable, List, Dict, Any


AI_PROVIDER_CHOICES = [
    ("Skip AI scan", None),
    ("Ollama", "ollama"),
    ("OpenAI", "openai"),
    ("AWS Bedrock", "bedrock"),
]


def get_openai_api_key() -> Optional[str]:
    """Return the configured OpenAI API key."""
    return (
        os.environ.get("OPENAI_KEY")
        or os.environ.get("TRUSCANNER_OPENAI_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )


def get_bedrock_access_key_id() -> Optional[str]:
    """Return the configured Bedrock access key id."""
    return os.environ.get("TRUSCANNER_ACCESS_KEY_ID") or os.environ.get("AWS_ACCESS_KEY_ID")


def get_bedrock_secret_access_key() -> Optional[str]:
    """Return the configured Bedrock secret access key."""
    return os.environ.get("TRUSCANNER_SECRET_ACCESS_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")


def get_bedrock_session_token() -> Optional[str]:
    """Return the configured Bedrock session token."""
    return os.environ.get("TRUSCANNER_SESSION_TOKEN") or os.environ.get("AWS_SESSION_TOKEN")


def get_bedrock_profile() -> Optional[str]:
    """Return the configured AWS profile for Bedrock."""
    return os.environ.get("TRUSCANNER_PROFILE") or os.environ.get("AWS_PROFILE")


def get_bedrock_region() -> Optional[str]:
    """Return the configured Bedrock region."""
    return (
        os.environ.get("TRUSCANNER_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
    )


def get_bedrock_model_id(model: Optional[str] = None, default: Optional[str] = None) -> Optional[str]:
    """Return the configured Bedrock model id."""
    return (
        model
        or
        os.environ.get("TRUSCANNER_MODEL_ID")
        or os.environ.get("AWS_BEDROCK_MODEL_ID")
        or os.environ.get("BEDROCK_MODEL_ID")
        or default
    )


def normalize_ai_provider(provider: Optional[str]) -> Optional[str]:
    """Normalize user-facing provider names to internal ids."""
    if provider is None:
        return None

    value = str(provider).strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "skip": None,
        "skip_ai_scan": None,
        "none": None,
        "ollama": "ollama",
        "openai": "openai",
        "aws_bedrock": "bedrock",
        "bedrock": "bedrock",
    }
    return mapping.get(value)


def has_openai_credentials() -> bool:
    """Return True when OpenAI credentials are available in the environment."""
    return bool(get_openai_api_key())


def has_bedrock_credentials() -> bool:
    """Return True when AWS Bedrock credentials and region are configured."""
    has_region = bool(get_bedrock_region())
    has_static_keys = bool(
        get_bedrock_access_key_id() and get_bedrock_secret_access_key()
    )
    has_profile = bool(get_bedrock_profile())
    return has_region and (has_static_keys or has_profile)


def get_missing_provider_requirements(provider: Optional[str]) -> List[str]:
    """List missing environment requirements for the selected AI provider."""
    normalized = normalize_ai_provider(provider)
    if normalized == "openai":
        return [] if has_openai_credentials() else ["OPENAI_KEY"]
    if normalized == "bedrock":
        missing = []
        if not get_bedrock_region():
            missing.append("TRUSCANNER_REGION")
        if not (
            (get_bedrock_access_key_id() and get_bedrock_secret_access_key())
            or get_bedrock_profile()
        ):
            missing.append("TRUSCANNER_ACCESS_KEY_ID and TRUSCANNER_SECRET_ACCESS_KEY")
        return missing
    return []


def get_ai_provider_setup_help(provider: Optional[str]) -> List[str]:
    """Return setup guidance for .env files or exported shell variables."""
    normalized = normalize_ai_provider(provider)
    if normalized == "openai":
        return [
            "Set credentials in `.env` or export them in your shell:",
            "  OPENAI_KEY=your-openai-key",
            "Shell example: export OPENAI_KEY=your-openai-key",
        ]
    if normalized == "bedrock":
        return [
            "Set AWS credentials in `.env` or export them in your shell:",
            "  TRUSCANNER_ACCESS_KEY_ID=your-access-key",
            "  TRUSCANNER_SECRET_ACCESS_KEY=your-secret-key",
            "  TRUSCANNER_REGION=us-east-1",
            "  TRUSCANNER_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0",
            "Shell example: export TRUSCANNER_ACCESS_KEY_ID=... TRUSCANNER_SECRET_ACCESS_KEY=... TRUSCANNER_REGION=us-east-1",
        ]
    if normalized == "ollama":
        return [
            "Ensure Ollama is running locally and at least one model is installed.",
            "Example: ollama pull llama3",
        ]
    return []


def resolve_default_ai_provider() -> str:
    """Choose the most likely provider default based on available configuration."""
    if has_openai_credentials():
        return "openai"
    if has_bedrock_credentials():
        return "bedrock"
    return "ollama"


def _fallback_select(message: str, options: List[str], default_index: int = 0) -> str:
    """Simple numeric selection fallback when inquirer is unavailable."""
    print(f"\n{message}")
    for i, option in enumerate(options, 1):
        print(f"{i}. {option}")

    choice = input(f"Enter choice (1-{len(options)}) [{default_index + 1}]: ").strip()
    choice = choice or str(default_index + 1)
    try:
        selected_index = int(choice) - 1
        if 0 <= selected_index < len(options):
            return options[selected_index]
    except ValueError:
        pass
    return options[default_index]


def select_file_format() -> str:
    """Interactive arrow-key menu for file format selection."""
    options = ['txt', 'md', 'json', 'All']
    try:
        from inquirer import prompt, List

        questions = [
            List('format',
                 message="Select output format:",
                 choices=options,
                 default='txt')
        ]
        answers = prompt(questions)
        if answers and 'format' in answers:
            return answers['format'].lower()
        return 'txt'  # Default fallback
    except ImportError:
        # If inquirer is not installed, show helpful message
        print("\n⚠️  Warning: inquirer not installed. Installing interactive menu support...")
        print("   Run: pip install inquirer")
        selection = _fallback_select("Select output format:", options)
        return selection.lower()
    except Exception as e:
        # If inquirer fails for other reasons, fall back gracefully
        print(f"\n⚠️  Interactive menu unavailable: {e}")
        selection = _fallback_select("Select output format:", options)
        return selection.lower()


def select_ai_provider(default_provider: Optional[str] = None) -> Optional[str]:
    """Interactive arrow-key menu for AI provider selection."""
    if default_provider is None:
        normalized_default = resolve_default_ai_provider()
    else:
        normalized_default = normalize_ai_provider(default_provider)
    options = [label for label, _ in AI_PROVIDER_CHOICES]
    default_label = next(
        (
            label
            for label, value in AI_PROVIDER_CHOICES
            if value == normalized_default
        ),
        AI_PROVIDER_CHOICES[0][0],
    )

    try:
        from inquirer import prompt, List

        questions = [
            List(
                'provider',
                message="Select enhanced AI scan provider:",
                choices=options,
                default=default_label,
            )
        ]
        answers = prompt(questions)
        selected_label = answers.get('provider') if answers else None
        for label, value in AI_PROVIDER_CHOICES:
            if label == selected_label:
                return value
        return None
    except ImportError:
        print("\n⚠️  Warning: inquirer not installed. Falling back to numeric selection.")
    except Exception as e:
        print(f"\n⚠️  Interactive menu unavailable: {e}")

    selection = _fallback_select("Select enhanced AI scan provider:", options)
    for label, value in AI_PROVIDER_CHOICES:
        if label == selection:
            return value
    return None


def select_ollama_model(available_models: List[str]) -> str:
    """Interactive arrow-key menu for Ollama model selection."""
    if not available_models:
        return 'llama3' # Fallback default
    
    if len(available_models) == 1:
        import click
        click.echo(f"\nUsing only available local model: {available_models[0]}")
        return available_models[0]

    try:
        from inquirer import prompt, List
        
        questions = [
            List('model',
                 message="Select Ollama model for enhanced scan:",
                 choices=available_models,
                 default=available_models[0])
        ]
        answers = prompt(questions)
        if answers and 'model' in answers:
            return answers['model']
        return available_models[0]
    except ImportError:
        selection = _fallback_select(
            "Multiple Ollama models found. Select one for enhanced scan:",
            available_models,
        )
        return selection
    except Exception as e:
        print(f"\n⚠️  Interactive menu unavailable: {e}")
        return available_models[0]


def show_progress(current: int, total: int, current_file: str):
    """Display progress bar and file count on a single line."""
    if total == 0:
        return
    
    percentage = (current / total * 100)
    bar_length = 40
    filled = int(bar_length * current / total)
    bar = '█' * filled + '░' * (bar_length - filled)
    
    # Truncate filename if too long
    file_display = current_file[:50] + "..." if len(current_file) > 50 else current_file
    
    # Use ANSI escape codes to clear the line and move cursor to beginning
    # This ensures we stay on one line
    sys.stdout.write('\r\033[K')  # \r = return to start, \033[K = clear to end of line
    sys.stdout.write(f'Scanning: {current}/{total} ({percentage:.1f}%) [{bar}] {file_display}')
    sys.stdout.flush()
    
    if current == total:
        sys.stdout.write('\n')  # New line only when complete
        sys.stdout.flush()


def upload_to_backend(scan_report_id: str, project_name: str, duration: float,
                     total_findings: int, scan_data: List[Dict], files_scanned: int,
                     metadata: Dict[str, Any]) -> bool:
    """Upload scan results to backend API."""
    import requests
    
    # Backend URL hardcoded
    backend_url = "https://d987tu7rq4.execute-api.ap-south-1.amazonaws.com"
    
    # Remove trailing slash
    backend_url = backend_url.rstrip('/')
    
    payload = {
        "scan_report_id": scan_report_id,
        "project_name": project_name,
        "duration_seconds": duration,
        "total_findings": total_findings,
        "scan_data": scan_data,
        "files_scanned": files_scanned,
        "metadata": metadata
    }
    
    try:
        print("\nUploading ...")
        response = requests.post(
            f"{backend_url}/api/scans/",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        return True
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Server is busy, not stored right now!")
        print(f"   Could not connect to {backend_url}")
        print(f"   Make sure the backend server is running.")
        return False
    except requests.exceptions.Timeout:
        print(f"\n❌ Server is busy, not stored right now!")
        print(f"   Request to {backend_url} timed out.")
        return False
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ Server is busy, not stored right now!")
        error_text = e.response.text[:100] if hasattr(e, 'response') and e.response else str(e)
        print(f"   HTTP {e.response.status_code if hasattr(e, 'response') else 'Unknown'}: {error_text}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Server is busy, not stored right now!")
        print(f"   Error: {str(e)}")
        return False
