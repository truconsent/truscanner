import os
import re
import hashlib
import random
from datetime import datetime
from pathlib import Path


def generate_report_id(directory_path: str) -> str:
    """Generate a 32-bit hash report ID for the scan session."""
    timestamp = datetime.now().isoformat()
    random_component = random.randint(1000, 9999)
    input_string = f"{timestamp}_{directory_path}_{random_component}"
    
    # Generate MD5 hash (32 hex characters)
    hash_obj = hashlib.md5(input_string.encode('utf-8'))
    return hash_obj.hexdigest()


def sanitize_directory_name(directory_path: str) -> str:
    """Convert directory path to safe folder name."""
    # Get last part of path
    name = os.path.basename(os.path.normpath(directory_path))
    # Replace invalid chars
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'\s+', '_', name)
    # Remove leading/trailing dots and underscores
    name = name.strip('._')
    # Ensure it's not empty
    if not name:
        name = "scan_results"
    return name


def get_reports_directory(base_dir: str = ".") -> Path:
    """Get or create Reports directory."""
    reports_dir = Path(base_dir) / "Reports"
    reports_dir.mkdir(exist_ok=True)
    return reports_dir


def get_next_report_filename(reports_subdir: Path, file_type: str) -> str:
    """Get next available filename with auto-increment."""
    base_name = "truscan_report"
    extensions = {"txt": ".txt", "md": ".md", "json": ".json"}
    
    if file_type not in extensions:
        raise ValueError(f"Invalid file type: {file_type}")
    
    extension = extensions[file_type]
    
    # Check for base file (no number)
    base_file = reports_subdir / f"{base_name}{extension}"
    if not base_file.exists():
        return f"{base_name}{extension}"
    
    # Find highest number
    max_num = 0
    pattern = re.compile(rf"^{re.escape(base_name)}(\d+){re.escape(extension)}$")
    
    for file in reports_subdir.iterdir():
        if file.is_file():
            match = pattern.match(file.name)
            if match:
                max_num = max(max_num, int(match.group(1)))
    
    return f"{base_name}{max_num + 1}{extension}"


def create_reports_subdirectory(reports_dir: Path, directory_name: str) -> Path:
    """Create subdirectory for reports with sanitized name."""
    sanitized_name = sanitize_directory_name(directory_name)
    subdir = reports_dir / sanitized_name
    subdir.mkdir(exist_ok=True)
    return subdir

