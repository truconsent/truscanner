import os
import re
import asyncio
from typing import List, Dict, Any
from .ai_scanner import scan_directory_ai

try:
    from presidio_analyzer import AnalyzerEngine
    PRESIDIO_AVAILABLE = True
except ImportError:
    PRESIDIO_AVAILABLE = False

# Define regex patterns for data elements
DATA_ELEMENTS = [
    {
        "name": "Email Address",
        "regex": r"(?i)\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z]{2,}\b",
        "category": "Contact Info",
        "sensitivity": "High"
    },
    {
        "name": "IPv4 Address",
        "regex": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "category": "Network Info",
        "sensitivity": "Medium"
    },
    {
        "name": "Credit Card Number",
        "regex": r"\b(?:\d{4}[- ]?){3}\d{4}\b",
        "category": "Financial",
        "sensitivity": "Critical"
    },
    {
        "name": "Social Security Number (US)",
        "regex": r"\b\d{3}-\d{2}-\d{4}\b",
        "category": "Government ID",
        "sensitivity": "Critical"
    },
    {
        "name": "API Key / Token",
        "regex": r"(?i)(api_key|apikey|secret|token)[\s=:'\"]+([A-Za-z0-9_\-]{16,})",
        "category": "Secrets",
        "sensitivity": "Critical"
    }
]

def scan_file(filepath: str, analyzer: Any = None) -> List[Dict[str, Any]]:
    findings = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        # 1. Regex Scanning
        lines = content.splitlines()
        for i, line in enumerate(lines):
            line_number = i + 1
            for element in DATA_ELEMENTS:
                if re.search(element["regex"], line):
                    findings.append({
                        "filename": filepath,
                        "line_number": line_number,
                        "element_name": element["name"],
                        "element_category": element["category"],
                        "isSensitive": element["sensitivity"] in ["High", "Critical"],
                        "sensitivity": element["sensitivity"],
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

def scan_directory(directory: str) -> List[Dict[str, Any]]:
    results = []
    
    # Initialize Presidio
    analyzer = None
    if PRESIDIO_AVAILABLE:
        try:
            analyzer = AnalyzerEngine()
        except Exception as e:
            print(f"Warning: Presidio initialization failed: {e}")

    # 1. Local Scan (Regex + Presidio)
    for root, _, files in os.walk(directory):
        for file in files:
            # Skip hidden files
            if not file.startswith('.'):
                filepath = os.path.join(root, file)
                results.extend(scan_file(filepath, analyzer))
    
    # 2. LLM Scan (OpenAI)
    if os.environ.get("OPENAI_API_KEY"):
        try:
            ai_results = asyncio.run(scan_directory_ai(directory))
            for item in ai_results:
                item["source"] = "LLM"
            results.extend(ai_results)
        except Exception as e:
            print(f"AI Scan failed: {e}")
            
    return results