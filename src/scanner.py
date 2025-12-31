import os
import asyncio
from typing import List, Dict, Any
from .regex_scanner import RegexScanner
from .ai_scanner import scan_directory_ai

try:
    from presidio_analyzer import AnalyzerEngine
    PRESIDIO_AVAILABLE = True
except ImportError:
    PRESIDIO_AVAILABLE = False

def scan_file(filepath: str, regex_scanner: RegexScanner = None, analyzer: Any = None) -> List[Dict[str, Any]]:
    findings = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        # 1. Regex Scanning using RegexScanner
        if regex_scanner:
            regex_findings = regex_scanner.scan_text(content, context=filepath)
            for finding in regex_findings:
                findings.append({
                    "filename": filepath,
                    "line_number": finding["line_number"],
                    "element_name": finding["element_name"],
                    "element_category": finding["element_category"],
                    "isSensitive": finding["isSensitive"],
                    "sensitivity": finding["sensitivity"],
                    "matched_text": finding.get("matched_text", ""),
                    "line_content": finding.get("line_content", ""),
                    "tags": finding.get("tags", {}),
                    "source": "Regex"
                })

        # 2. Presidio Scanning
        if analyzer and PRESIDIO_AVAILABLE:
            results = analyzer.analyze(text=content, language='en')
            for res in results:
                line_number = content[:res.start].count('\n') + 1
                findings.append({
                    "filename": filepath,
                    "line_number": line_number,
                    "element_name": res.entity_type,
                    "element_category": "PII",
                    "isSensitive": True,
                    "sensitivity": "High",
                    "source": "Presidio"
                })
    except Exception:
        # Skip files that cannot be read
        pass
    return findings

def scan_directory(directory: str, use_presidio: bool = False, use_ai: bool = False) -> List[Dict[str, Any]]:
    results = []
    
    # Initialize RegexScanner
    regex_scanner = RegexScanner()
    
    # Initialize Presidio (optional)
    analyzer = None
    if use_presidio and PRESIDIO_AVAILABLE:
        try:
            print("Initializing Presidio NLP scanner...")
            analyzer = AnalyzerEngine()
            print("✓ Presidio initialized")
        except Exception as e:
            print(f"Warning: Presidio initialization failed: {e}")
    elif use_presidio and not PRESIDIO_AVAILABLE:
        print("Warning: Presidio not available. Install with: pip install presidio-analyzer")

    # 1. Local Scan (Regex + optional Presidio)
    for root, _, files in os.walk(directory):
        for file in files:
            # Skip hidden files
            if not file.startswith('.'):
                filepath = os.path.join(root, file)
                results.extend(scan_file(filepath, regex_scanner, analyzer))
    
    # 2. LLM Scan (OpenAI) - optional
    if use_ai and os.environ.get("OPENAI_API_KEY"):
        try:
            print("Running AI scan...")
            ai_results = asyncio.run(scan_directory_ai(directory))
            for item in ai_results:
                item["source"] = "LLM"
            results.extend(ai_results)
        except Exception as e:
            print(f"AI Scan failed: {e}")
    elif use_ai and not os.environ.get("OPENAI_API_KEY"):
        print("Warning: AI scan requested but OPENAI_API_KEY not set")
            
    return results