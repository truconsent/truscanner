"""Utility functions for interactive menu, progress display, and backend integration."""
import os
import sys
from typing import Optional, Callable, List, Dict, Any


def select_file_format() -> str:
    """Interactive arrow-key menu for file format selection."""
    try:
        from inquirer import prompt, List
        
        questions = [
            List('format',
                 message="Select output format:",
                 choices=['txt', 'md', 'json', 'All'],
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
        print("\nFalling back to simple selection:")
        print("1. txt")
        print("2. md")
        print("3. json")
        print("4. All")
        choice = input("Enter choice (1-4) [1]: ").strip() or "1"
        
        choices_map = {"1": "txt", "2": "md", "3": "json", "4": "all"}
        return choices_map.get(choice, "txt")
    except Exception as e:
        # If inquirer fails for other reasons, fall back gracefully
        print(f"\n⚠️  Interactive menu unavailable: {e}")
        print("Falling back to simple selection:")
        print("1. txt")
        print("2. md")
        print("3. json")
        print("4. All")
        choice = input("Enter choice (1-4) [1]: ").strip() or "1"
        choices_map = {"1": "txt", "2": "md", "3": "json", "4": "all"}
        return choices_map.get(choice, "txt")


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
        print("\nMultiple models found. Select one for enhanced scan:")
        for i, model in enumerate(available_models, 1):
            print(f"{i}. {model}")
        
        choice = input(f"Enter choice (1-{len(available_models)}) [1]: ").strip() or "1"
        try:
            index = int(choice) - 1
            if 0 <= index < len(available_models):
                return available_models[index]
            return available_models[0]
        except (ValueError, IndexError):
            return available_models[0]
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

