import os
import re
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict
import concurrent.futures
import bisect


# Global variables for workers
_worker_data_elements = []

class RegexScanner:
    """Scanner that uses regex patterns from JSON files to identify privacy data elements."""
    
    DEFAULT_EXCLUDE_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build', '.next', '.cache'}
    DEFAULT_EXCLUDE_FILES = {
        'tsconfig.node.json', 'tsconfig.app.json', 'tsconfig.json', 
        'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'bun.lock', 
        'tailwind.config.ts', 'tailwind.config.js', 'package.json',
        '.DS_Store', 'vite.config.ts', 'vite.config.js', 'eslint.config.js', 'tsconfig.json'
    }
    DEFAULT_EXCLUDE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.pdf', '.zip', '.gz', '.tar', '.log', '.css', '.db', '.sqlite', '.sqlite3', '.bin', '.exe', '.dll', '.so', '.dylib'}
    SENSITIVITY_EMOJI = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
    
    def __init__(self, data_elements_dir: Optional[str] = None, load_immediately: bool = True):
        """Initialize scanner with data element patterns."""
        if data_elements_dir is None:
            data_elements_dir = Path(__file__).parent.parent / "data_elements"
        
        self.data_elements_dir = Path(data_elements_dir)
        self.data_elements = []
        if load_immediately:
            self._load_data_elements()
    
    def _load_data_elements(self):
        """Load patterns from JSON files."""
        if self.data_elements_dir.exists():
            for json_file in self.data_elements_dir.rglob("*.json"):
                self._parse_json_file(json_file)

    def _parse_json_file(self, json_file: Path):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for source in data.get("sources", []):
                compiled_patterns = []
                keywords = set()
                for pattern in source.get("patterns", []):
                        try:
                            compiled_patterns.append(re.compile(pattern))
                            # Extract words of 3+ chars as potential keywords for skipping
                            # Clean the pattern of escape sequences (like \b, \s, \w)
                            clean_pattern = re.sub(r'\\[a-zA-Z]', ' ', pattern)
                            words = re.findall(r'[a-zA-Z]{3,}', clean_pattern)
                            for w in words:
                                if len(w) >= 3:
                                    keywords.add(w.lower())
                            if '@' in pattern:
                                keywords.add('@')
                        except re.error:
                            # Skip invalid regexes silently to avoid flooding output
                            continue
                    
                if compiled_patterns:
                    element_info = {
                        "name": source["name"],
                        "category": source["category"],
                        "isSensitive": source.get("isSensitive", False),
                        "sensitivity": source.get("sensitivity", "low"),
                        "patterns": compiled_patterns,
                        "keywords": list(keywords),
                        "tags": source.get("tags", {})
                    }
                    self.data_elements.append(element_info)
        except Exception as e:
            print(f"Error loading {json_file}: {e}")
    
    def _is_false_positive(self, line_content: str, matched_text: str, match_start: int, line_start: int) -> bool:
        """Check if a match is likely a false positive."""
        line_lower = line_content.lower()
        matched_lower = matched_text.lower().strip()
        line_stripped = line_content.strip()
        
        # Skip matches in comments (both // and #)
        comment_idx = line_content.find("//")
        if comment_idx == -1:
            comment_idx = line_content.find("#")
        if comment_idx != -1 and (match_start - line_start) > comment_idx:
            return True
        
        # Skip matches in multi-line comments
        if line_stripped.startswith(("*", "/*", "*/")):
            return True
        
        # Skip HTML attributes and CSS values
        if any(html_attr in line_lower for html_attr in [
            'device-width', 'device-height', 'apple-touch-icon', 
            'viewport', 'meta name', 'content=', 'rel='
        ]):
            return True
        
        # Skip CSS font-family and similar
        if 'font-family' in line_lower or 'google fonts' in line_lower:
            return True
        
        # Skip common false positives for device, google, apple
        if matched_lower in ['device', 'google', 'apple']:
            if any(term in line_lower for term in ['width', 'height', 'touch-icon', 'font', 'meta']):
                return True
        
        # Calculate position in line
        match_pos = match_start - line_start
        before_match = line_content[:match_pos].strip()
        after_match = line_content[match_pos + len(matched_text):].strip()
        
        # Skip if match is in a string that's clearly not personal data
        # (e.g., "email field", "phone number field")
        if re.search(r'["\']\s*(email|phone|name|address)\s*(field|column|attribute|property)', line_lower):
            return True
        
        # Skip SQL field names (SELECT, INSERT, UPDATE statements) - field names only
        if re.search(r'\b(SELECT|INSERT\s+INTO|UPDATE\s+\w+\s+SET)\s+', line_content, re.IGNORECASE):
            # If it's in a SQL query string, check if it's just field names
            if '"' in line_content or "'" in line_content:
                # Check if match is inside quotes (SQL query string)
                quote_start = max(line_content.rfind('"', 0, match_pos), line_content.rfind("'", 0, match_pos))
                quote_end = min(
                    line_content.find('"', match_pos) if line_content.find('"', match_pos) != -1 else len(line_content),
                    line_content.find("'", match_pos) if line_content.find("'", match_pos) != -1 else len(line_content)
                )
                if quote_start != -1 and quote_end > match_pos:
                    # It's in a SQL query string - likely just field names
                    return True
        
        # Skip function parameters that are just variable names
        if re.search(r'\bfunction\s+\w+\s*\([^)]*\b' + re.escape(matched_text) + r'\b', line_content, re.IGNORECASE):
            return True
        
        # Skip object property definitions without actual values (empty strings, null, undefined)
        if re.search(r'\b' + re.escape(matched_text) + r'\s*[:=]\s*["\']?\s*[,}]', line_content, re.IGNORECASE):
            return True
        
        # Skip return statements with just variable names
        if re.search(r'\breturn\s+' + re.escape(matched_text) + r'\s*[;,]', line_content, re.IGNORECASE):
            return True
        
        # Only match actual email addresses (with @), not just the word "email"
        if matched_lower == "email" and "@" not in line_content:
            # Check if it's followed by actual email pattern
            if not re.search(r'email\s*[:=]\s*["\']?[^"\']*@', line_content, re.IGNORECASE):
                return True
        
        # Only match actual phone numbers (with digits), not just the word "phone"
        if matched_lower in ["phone", "mobile"] and not re.search(r'\d{6,}', line_content):
            # Check if it's followed by actual phone pattern
            if not re.search(r'(phone|mobile)\s*[:=]\s*["\']?[^"\']*\d{6,}', line_content, re.IGNORECASE):
                return True
        
        # Skip variable declarations without actual values (just variable names)
        # e.g., "const email" or "let phone" without assignment
        if re.search(r'\b(const|let|var)\s+' + re.escape(matched_text) + r'\s*[;,]', line_content, re.IGNORECASE):
            return True
        
        # Only match if there's actual data (quoted strings with content, or actual patterns)
        # Skip if it's just a variable name in an assignment without a value
        if re.search(r'\b' + re.escape(matched_text) + r'\s*=\s*["\']?\s*[;,\n]', line_content, re.IGNORECASE):
            return True
        
        return False

    def scan_text(self, text: str, context: str = "") -> List[Dict[str, Any]]:
        """Scan text for data elements and return findings efficiently."""
        findings = []
        if not text:
            return findings

        # Precompute line start offsets for fast offset-to-line lookup
        line_starts = [0]
        for match in re.finditer(r'\n', text):
            line_starts.append(match.end())
        
        lines = None # Lazy split if needed
        text_lower = None

        for element in self.data_elements:
            # OPTIMIZATION: Skip element if none of its keywords are in the text
            if element.get("keywords"):
                if text_lower is None:
                    text_lower = text.lower()
                if not any(kw in text_lower for kw in element["keywords"]):
                    continue

            matched_lines_for_element = set()
            for pattern in element["patterns"]:
                for match in pattern.finditer(text):
                    start_offset = match.start()
                    # Find line number (1-indexed)
                    line_number = bisect.bisect_right(line_starts, start_offset)
                    
                    # One match per element per line to match previous behavior
                    if line_number in matched_lines_for_element:
                        continue
                    matched_lines_for_element.add(line_number)

                    if lines is None:
                        lines = text.splitlines()
                    
                    line_content = lines[line_number - 1] if line_number <= len(lines) else ""
                    line_start = line_starts[line_number - 1] if line_number > 0 else 0
                    
                    # Check for false positives
                    if self._is_false_positive(line_content, match.group(0), start_offset, line_start):
                        continue
                    
                    findings.append({
                        "line_number": line_number,
                        "line_content": line_content.strip(),
                        "matched_text": match.group(0),
                        "element_name": element["name"],
                        "element_category": element["category"],
                        "isSensitive": element["isSensitive"],
                        "sensitivity": element["sensitivity"],
                        "tags": element.get("tags", {}),
                        "context": context,
                        "source": "Regex"
                    })
        return findings
    
    def scan_file(self, filepath: str) -> List[Dict[str, Any]]:
        """Scan a single file and return findings."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                findings = self.scan_text(f.read(), context=filepath)
            
            for finding in findings:
                finding["filename"] = filepath
            
            return findings
        except Exception as e:
            print(f"Error scanning {filepath}: {e}")
            return []
    
    def scan_directory(self, directory: str, extensions: Optional[List[str]] = None,
                       exclude_dirs: Optional[set] = None) -> List[Dict[str, Any]]:
        """Recursively scan directory or file for data elements with parallel processing."""
        path = Path(directory)
        
        if not path.exists():
            print(f"Error: Path not found: {directory}")
            return []
        
        if path.is_file():
            return self.scan_file(str(path))
        
        exclude_dirs = exclude_dirs or self.DEFAULT_EXCLUDE_DIRS
        exclude_files = self.DEFAULT_EXCLUDE_FILES
        exclude_exts = self.DEFAULT_EXCLUDE_EXTENSIONS
        
        files_to_scan = []
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
            
            for file in files:
                if file.startswith('.') or file in exclude_files:
                    continue
                
                if any(file.endswith(ext) for ext in exclude_exts):
                    continue
                    
                if extensions and not any(file.endswith(ext) for ext in extensions):
                    continue
                
                files_to_scan.append(os.path.join(root, file))
        
        all_findings = []
        
        # Sequential scanning to avoid Windows multiprocessing issues
        # For better performance on large codebases, consider using ThreadPoolExecutor
        if not self.data_elements:
            self._load_data_elements()
            
        for file_path in files_to_scan:
            try:
                file_findings = self.scan_file(file_path)
                all_findings.extend(file_findings)
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
        
        return all_findings
    
    def generate_report(self, findings: List[Dict[str, Any]], duration: Optional[float] = None) -> str:
        """Generate formatted report from findings."""
        if not findings:
            return "No data elements found."
        
        header = [
            "=" * 80,
            "TRUSCANNER REPORT",
            "=" * 80,
            f"\nTotal Findings: {len(findings)}"
        ]
        
        if duration is not None:
            header.append(f"Time Taken: {duration:.2f} seconds")
            
        header.extend([
            "",
            "-" * 80
        ])
        
        lines = header
        
        # Group by file
        by_file = defaultdict(list)
        for f in findings:
            by_file[f.get("filename", "Unknown")].append(f)
        
        # File details
        for filename, file_findings in by_file.items():
            lines.extend([
                f"\n📄 File: {filename}",
                f"   Found {len(file_findings)} data element(s)\n"
            ])
            
            for finding in file_findings:
                emoji = self.SENSITIVITY_EMOJI.get(finding["sensitivity"].lower(), "⚪")
                lines.extend([
                    f"   {emoji} Line {finding['line_number']}: {finding['element_name']}",
                    f"      Category: {finding['element_category']}",
                    f"      Sensitivity: {finding['sensitivity']}",
                    f"      Matched: {finding['matched_text']}",
                    f"      Context: {finding['line_content'][:100]}"
                ])
                
                if finding.get("tags"):
                    tags = ", ".join(f"{k}: {v}" for k, v in finding["tags"].items())
                    lines.append(f"      Tags: {tags}")
                
                lines.append("")
            
            lines.append("-" * 80)
        
        # Summaries
        category_details = defaultdict(lambda: defaultdict(int))
        sensitivity_counts = defaultdict(int)
        
        for f in findings:
            category_details[f["element_category"]][f["element_name"]] += 1
            sensitivity_counts[f["sensitivity"]] += 1
        
        lines.append("\n📊 SUMMARY BY CATEGORY\n")
        for category, elements in sorted(category_details.items(), key=lambda x: sum(x[1].values()), reverse=True):
            total_count = sum(elements.values())
            distinct_count = len(elements)
            lines.append(f"   {category}: {total_count} ({distinct_count} distinctive elements)")
            for name, count in sorted(elements.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"      - {name}: {count}")
        
        lines.append("\n🔒 SUMMARY BY SENSITIVITY\n")
        for sensitivity, count in sorted(sensitivity_counts.items()):
            lines.append(f"   {sensitivity.capitalize()}: {count}")

        lines.append("\n" + "=" * 80)
        return "\n".join(lines)


def main():
    """CLI entry point for standalone usage."""
    import time
    
    if len(sys.argv) < 2:
        print("Usage: python regex_scanner.py <directory_to_scan>")
        sys.exit(1)
    
    scanner = RegexScanner()
    
    start_time = time.time()
    findings = scanner.scan_directory(sys.argv[1])
    duration = time.time() - start_time
    
    report = scanner.generate_report(findings, duration=duration)
    
    print(f"\nScanning: {sys.argv[1]}\n")
    print(report)
    
    output_file = "regex_scan_report.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n✅ Report saved to: {output_file}")


def _parallel_scan_file(filepath: str) -> List[Dict[str, Any]]:
    """Standalone worker function for ProcessPoolExecutor. Uses global pre-loaded patterns."""
    global _worker_data_elements
    try:
        data_elements = _worker_data_elements
        
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        
        if not text:
            return []

        findings = []
        line_starts = [0]
        for match in re.finditer(r'\n', text):
            line_starts.append(match.end())
        
        lines = None
        text_lower = text.lower()

        # Identify Data Elements
        for element in data_elements:
            if element.get("keywords"):
                if not any(kw in text_lower for kw in element["keywords"]):
                    continue

            matched_lines_for_element = set()
            for pattern in element["patterns"]:
                for match in pattern.finditer(text):
                    start_offset = match.start()
                    line_number = bisect.bisect_right(line_starts, start_offset)
                    
                    if line_number in matched_lines_for_element:
                        continue
                    matched_lines_for_element.add(line_number)

                    if lines is None:
                        lines = text.splitlines()
                    
                    line_content = lines[line_number - 1] if line_number <= len(lines) else ""
                    line_content_stripped = line_content.strip()
                    
                    # Heuristic: Skip findings that are likely just comments or in noisy files
                    if any(filepath.endswith(skip) for skip in [".txt", ".md", ".json", "robots.txt"]):
                         # Allow specific matches if needed, but for now skip noisy ones like User Agent in robots.txt
                         if element["name"] in ["User Agent String", "Cookies"]:
                             continue

                    # Skip matches in single-line comments (if match is after // or #)
                    line_offset = match.start() - line_starts[line_number - 1]
                    comment_idx = line_content.find("//")
                    if comment_idx == -1:
                        comment_idx = line_content.find("#")
                    
                    if comment_idx != -1 and line_offset > comment_idx:
                        continue
                    
                    if line_content_stripped.startswith(("*", "/*")):
                        continue

                    finding = {
                        "line_number": line_number,
                        "line_content": line_content.strip(),
                        "matched_text": match.group(0),
                        "element_name": element["name"],
                        "element_category": element["category"],
                        "isSensitive": element["isSensitive"],
                        "sensitivity": element["sensitivity"],
                        "tags": element["tags"],
                        "context": filepath,
                        "filename": filepath,
                        "source": "Regex"
                    }
                    findings.append(finding)
        return findings
    except Exception as e:
        print(f"Error scanning {filepath}: {e}")
        return []


if __name__ == "__main__":
    main()
