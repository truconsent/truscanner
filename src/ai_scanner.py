import os
import json
import asyncio
import time
import sys
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional
import ollama
from openai import OpenAI

class AIScanner:
    """Scanner that uses LLMs (Ollama or OpenAI) to identify privacy data elements."""
    
    def __init__(self, data_elements_dir: Optional[str] = None):
        if data_elements_dir is None:
            data_elements_dir = Path(__file__).parent.parent / "data_elements"
        self.data_elements_dir = Path(data_elements_dir)
        self.data_elements_names = self._load_data_elements_names()
        self.selected_model = "Unknown"

    def _load_data_elements_names(self) -> List[str]:
        """Load all data element names from JSON files for context."""
        names = []
        if self.data_elements_dir.exists():
            for json_file in self.data_elements_dir.rglob("*.json"):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    for source in data.get("sources", []):
                        names.append(source["name"])
                except Exception as e:
                    print(f"Error loading {json_file} for AI context: {e}")
        return names

    def _get_prompt(self, file_content: str, filename: str) -> str:
        """Construct the prompt for the LLM."""
        elements_list = ", ".join(self.data_elements_names[:100]) # Truncate if too many for context
        
        prompt = f"""
Analyze the code from '{filename}' and find Personal Identifiable Information (PII).

Identify these data types:
- Names (First Name, Last Name)
- Contact Info (Email, Phone, Address)
- Digital IDs (IP Address, CookieID)
- Data stored in Databases, LocalStorage, or Cookies.

Use these data element types for guidance: {elements_list}...

Return a JSON list of objects. Each object MUST have:
- "line_number": (int)
- "line_content": (string)
- "matched_text": (string) The specific PII text found
- "element_name": (string) e.g., "Email Address"
- "element_category": (string) e.g., "Contact Information"
- "reason": (string) Why it's a concern

ONLY return the JSON list, no other text.

Code Content:
{file_content}
"""
        return prompt

    def get_available_ollama_models(self) -> List[str]:
        """Fetch list of available model names from Ollama."""
        try:
            models_info = ollama.list()
            # Handle both list of Model objects and old-style response if any
            if hasattr(models_info, 'models'):
                return [m.model for m in models_info.models]
            elif isinstance(models_info, list):
                return [m.get('name') or m.model for m in models_info]
            return []
        except Exception as e:
            print(f"Error listing Ollama models: {e}")
            return []

    def scan_file(self, filepath: str, use_openai: bool = False, model: Optional[str] = None) -> List[Dict[str, Any]]:
        """Scan a single file using the selected LLM."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            if not content.strip():
                return []

            prompt = self._get_prompt(content, filepath)
            
            if use_openai and os.environ.get("OPENAI_API_KEY"):
                self.selected_model = "gpt-4o"
                return self._scan_with_openai(prompt, filepath)
            else:
                self.selected_model = model or "llama3"
                return self._scan_with_ollama(prompt, filepath, model=self.selected_model)

        except Exception as e:
            print(f"Error scanning {filepath} with AI: {e}")
            return []

    def _scan_with_ollama(self, prompt: str, filepath: str, model: Optional[str] = None) -> List[Dict[str, Any]]:
        """Call Ollama for analysis with a real-time timer."""
        if not model:
            model = 'llama3' # Fallback
            
        try:
            result = {"response": None, "error": None}
            
            def chat_thread():
                try:
                    res = ollama.chat(model=model, messages=[
                        {
                            'role': 'user',
                            'content': prompt,
                        },
                    ])
                    result["response"] = res
                except Exception as e:
                    result["error"] = e

            t = threading.Thread(target=chat_thread)
            t.start()
            
            start_time = time.time()
            while t.is_alive():
                elapsed = time.time() - start_time
                sys.stdout.write(f"\rAI Scanning: {filepath}... ({elapsed:.1f}s taken)")
                sys.stdout.flush()
                time.sleep(0.1)
            
            # Final line clear or update
            sys.stdout.write(f"\r✓ AI Scanned: {filepath} ({time.time() - start_time:.1f}s)\n")
            sys.stdout.flush()

            if result["error"]:
                raise result["error"]
                
            if not result["response"]:
                return []
                
            content = result["response"]['message']['content']
            return self._parse_llm_response(content, filepath)
        except Exception as e:
            print(f"Ollama error: {e}")
            return []

    def _scan_with_openai(self, prompt: str, filepath: str) -> List[Dict[str, Any]]:
        """Call OpenAI for analysis with a real-time timer."""
        try:
            result = {"response": None, "error": None}
            
            def chat_thread():
                try:
                    client = OpenAI()
                    res = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"}
                    )
                    result["response"] = res
                except Exception as e:
                    result["error"] = e

            t = threading.Thread(target=chat_thread)
            t.start()
            
            start_time = time.time()
            while t.is_alive():
                elapsed = time.time() - start_time
                sys.stdout.write(f"\rAI Scanning: {filepath}... ({elapsed:.1f}s taken)")
                sys.stdout.flush()
                time.sleep(0.1)
            
            sys.stdout.write(f"\r✓ AI Scanned: {filepath} ({time.time() - start_time:.1f}s)\n")
            sys.stdout.flush()

            if result["error"]:
                raise result["error"]
                
            if not result["response"]:
                return []
                
            content = result["response"].choices[0].message.content
            return self._parse_llm_response(content, filepath)
        except Exception as e:
            print(f"OpenAI error: {e}")
            return []

    def _parse_llm_response(self, content: str, filepath: str) -> List[Dict[str, Any]]:
        """Parse JSON from LLM response with robustness."""
        try:
            # More robust JSON extraction using regex
            import re
            # Look for the first '[' and last ']' to extract a potential JSON list
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if not match:
                # If no list, maybe it's an object with a findings key
                match = re.search(r'\{.*\}', content, re.DOTALL)
            
            if match:
                json_str = match.group(0)
                try:
                    raw_findings = json.loads(json_str)
                except json.JSONDecodeError:
                    # Try to sanitize trailing commas or other minor issues
                    json_str = re.sub(r',(\s*[\]}])', r'\1', json_str)
                    raw_findings = json.loads(json_str)
                
                # Handle both list responses and object responses with a "findings" key
                findings_list = []
                if isinstance(raw_findings, list):
                    findings_list = raw_findings
                elif isinstance(raw_findings, dict):
                    # Check for common keys
                    findings_list = raw_findings.get("findings", 
                                    raw_findings.get("data_elements", 
                                    raw_findings.get("data", [])))
                
                if not isinstance(findings_list, list):
                    return []
                
                validated_findings = []
                for f in findings_list:
                    if not isinstance(f, dict):
                        continue
                    
                    # Ensure required fields exist with defaults
                    valid_f = {
                        "line_number": int(f.get("line_number", 0)),
                        "line_content": f.get("line_content", f.get("context", "")),
                        "matched_text": f.get("matched_text") or f.get("matched") or "",
                        "element_name": f.get("element_name", "Unknown PII"),
                        "element_category": f.get("element_category", "Privacy"),
                        "reason": f.get("reason", ""),
                        "filename": filepath,
                        "source": f"LLM ({self.selected_model})"
                    }
                    validated_findings.append(valid_f)
                return validated_findings
            
            if content.strip():
                print(f"⚠️ No JSON found in LLM response for {filepath}")
                # print(f"Raw response: {content[:200]}...") # Uncomment for deep debugging
            return []
        except Exception as e:
            print(f"Error parsing LLM response for {filepath}: {e}")
            # print(f"Raw response: {content}") # Uncomment for deep debugging
            return []

    def scan_directory(self, directory: str, use_openai: bool = False, model: Optional[str] = None) -> List[Dict[str, Any]]:
        """Scan all files in a directory using AI."""
        all_findings = []
        path = Path(directory)
        
        from .regex_scanner import RegexScanner
        regex = RegexScanner()
        
        files_to_scan = []
        if path.is_file():
            files_to_scan = [str(path)]
        else:
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in regex.DEFAULT_EXCLUDE_DIRS and not d.startswith('.')]
                for file in files:
                    if file.startswith('.') or file in regex.DEFAULT_EXCLUDE_FILES:
                        continue
                    if any(file.endswith(ext) for ext in regex.DEFAULT_EXCLUDE_EXTENSIONS):
                        continue
                    files_to_scan.append(os.path.join(root, file))

        for file_path in files_to_scan:
            # The scanning message and timer are now handled inside the scanner methods
            file_findings = self.scan_file(file_path, use_openai=use_openai, model=model)
            all_findings.extend(file_findings)
            
        return all_findings

async def scan_directory_ai(directory: str) -> List[Dict[str, Any]]:
    """Backward compatible wrapper for AIScanner."""
    scanner = AIScanner()
    use_openai = bool(os.environ.get("OPENAI_API_KEY"))
    # Note: AIScanner.scan_directory is synchronous, but the original was async.
    # We call it in a thread to keep the async interface if needed, or just run it.
    return scanner.scan_directory(directory, use_openai=use_openai)
