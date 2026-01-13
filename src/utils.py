"""Utility functions for interactive menu, progress display, and backend integration."""
import os
import sys
from typing import Optional, Callable, List, Dict, Any
from dotenv import load_dotenv


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
            selected = answers['format']
            # Convert "All" to "all" for consistency
            return selected.lower() if selected.lower() == 'all' else selected.lower()
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


def show_progress(current: int, total: int, current_file: str):
    """Display progress bar and file count."""
    if total == 0:
        return
    
    percentage = (current / total * 100)
    bar_length = 40
    filled = int(bar_length * current / total)
    bar = '█' * filled + '░' * (bar_length - filled)
    
    # Truncate filename if too long
    file_display = current_file[:50] + "..." if len(current_file) > 50 else current_file
    
    # Clear previous line and print new progress
    print(f'\rScanning: {current}/{total} ({percentage:.1f}%) [{bar}] {file_display}', end='', flush=True)
    
    if current == total:
        print()  # New line when complete


def upload_to_backend(scan_report_id: str, project_name: str, duration: float,
                     total_findings: int, scan_data: List[Dict], files_scanned: int,
                     metadata: Dict[str, Any]) -> bool:
    """Upload scan results to backend API."""
    import requests
    
    # Load environment variables
    load_dotenv()
    backend_url = os.getenv('TRUSCANNER_BACKEND_URL')
    
    if not backend_url:
        print("\n⚠️  Backend URL not configured.")
        print("   Set TRUSCANNER_BACKEND_URL in .env file to enable backend upload.")
        print("   Example: TRUSCANNER_BACKEND_URL=http://localhost:8000")
        return False
    
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
        print(f"\n📤 Uploading to backend: {backend_url}/api/scans/")
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

