import os
import asyncio
from pathlib import Path
from typing import List, Dict, Any
from .regex_scanner import RegexScanner
from .ai_scanner import scan_directory_ai

def scan_file(filepath: str, regex_scanner: RegexScanner = None) -> List[Dict[str, Any]]:
    findings = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        # Regex Scanning using RegexScanner
        if regex_scanner:
            regex_findings = regex_scanner.scan_text(content, context=filepath)
            for finding in regex_findings:
                findings.append({
                    "filename": filepath,
                    "line_number": finding["line_number"],
                    "element_name": finding["element_name"],
                    "element_category": finding["element_category"],
                    "matched_text": finding.get("matched_text", ""),
                    "line_content": finding.get("line_content", ""),
                    "tags": finding.get("tags", {}),
                    "source": "Regex"
                })

    except Exception:
        # Skip files that cannot be read
        pass
    return findings

def scan_directory(directory: str, use_ai: bool = False, ai_mode: str = "balanced") -> List[Dict[str, Any]]:
    results = []
    
    # Initialize RegexScanner
    regex_scanner = RegexScanner()
    exclude_dirs = regex_scanner.DEFAULT_EXCLUDE_DIRS
    exclude_files = regex_scanner.DEFAULT_EXCLUDE_FILES
    exclude_exts = regex_scanner.DEFAULT_EXCLUDE_EXTENSIONS
    allowed_extensions = regex_scanner.DEFAULT_CODE_EXTENSIONS
    
    # 1. Local Scan (Regex)
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
        for file in files:
            if file.startswith('.') or file in exclude_files:
                continue
            file_ext = Path(file).suffix.lower()
            if file_ext in exclude_exts:
                continue
            if file_ext not in allowed_extensions:
                continue
            filepath = os.path.join(root, file)
            results.extend(scan_file(filepath, regex_scanner))
    
    # 2. LLM Scan (OpenAI) - optional
    if use_ai and os.environ.get("OPENAI_API_KEY"):
        try:
            print("Running AI scan...")
            ai_results = asyncio.run(scan_directory_ai(directory, ai_mode=ai_mode))
            for item in ai_results:
                item["source"] = "LLM"
            results.extend(ai_results)
        except Exception as e:
            print(f"AI Scan failed: {e}")
    elif use_ai and not os.environ.get("OPENAI_API_KEY"):
        print("Warning: AI scan requested but OPENAI_API_KEY not set")
            
    return results
