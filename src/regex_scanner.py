import os
import re
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from collections import defaultdict
import concurrent.futures
import bisect


# Global variables for workers
_worker_data_elements = []

class RegexScanner:
    """Scanner that uses regex patterns from JSON files to identify privacy data elements."""
    
    DEFAULT_EXCLUDE_DIRS = {
        '.git',
        'node_modules',
        '__pycache__',
        '.venv',
        'venv',
        'dist',
        'build',
        '.next',
        '.cache',
        'reports',
    }
    DEFAULT_CODE_EXTENSIONS = {
        '.py', '.pyi',
        '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx',
        '.c', '.h', '.cpp', '.cc', '.cxx', '.hpp', '.hh', '.hxx',
        '.java', '.cs', '.go', '.rs', '.rb', '.php',
        '.swift', '.kt', '.kts', '.scala', '.sc',
        '.dart', '.lua', '.r', '.pl', '.pm',
        '.sh', '.bash', '.zsh', '.ps1', '.bat', '.cmd',
        '.sql', '.vue', '.svelte'
    }
    
    @staticmethod
    def _strip_directory_prefix(file_path: str, base_directory: Optional[str]) -> str:
        """Strip the base directory prefix from a file path."""
        if not base_directory:
            return file_path
        
        # Normalize paths
        file_path_norm = os.path.normpath(file_path)
        base_dir_norm = os.path.normpath(base_directory)
        
        # Check if file path starts with base directory
        if file_path_norm.startswith(base_dir_norm):
            # Remove base directory prefix
            relative = file_path_norm[len(base_dir_norm):]
            # Ensure it starts with path separator
            if not relative.startswith(os.sep) and not relative.startswith('/'):
                relative = os.sep + relative
            return relative
        
        return file_path
    DEFAULT_EXCLUDE_FILES = {
        'tsconfig.node.json', 'tsconfig.app.json', 'tsconfig.json', 
        'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'bun.lock', 
        'tailwind.config.ts', 'tailwind.config.js', 'package.json',
        '.DS_Store', 'vite.config.ts', 'vite.config.js', 'eslint.config.js', 'tsconfig.json'
    }
    DEFAULT_EXCLUDE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.pdf', '.zip', '.gz', '.tar', '.log', '.css', '.db', '.sqlite', '.sqlite3', '.bin', '.exe', '.dll', '.so', '.dylib'}
    
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
        
        # Skip entire lines that are comments (start with //, #, /*, or *)
        if line_stripped.startswith(("//", "#", "/*", "*/", "*")):
            return True
        
        # Skip matches in single-line comments (both // and #)
        # Check if the match is after a comment marker
        comment_idx = line_content.find("//")
        if comment_idx == -1:
            comment_idx = line_content.find("#")
        if comment_idx != -1:
            match_pos = match_start - line_start
            # If match is after comment marker, skip it
            if match_pos > comment_idx:
                return True
            # If comment marker is before match and there's no code before comment, skip entire line
            if comment_idx < match_pos and not line_content[:comment_idx].strip():
                return True
        
        # Skip matches in multi-line comments (/* ... */)
        # Check if we're inside a /* */ block
        before_match = line_content[:match_start - line_start]
        if "/*" in before_match:
            # Find the last /* before the match
            comment_start = before_match.rfind("/*")
            # Check if there's a closing */ after the comment start but before match
            comment_end = line_content.find("*/", comment_start)
            if comment_end == -1 or comment_end > match_start - line_start:
                # We're inside a comment block
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
                    line_stripped = line_content.strip()
                    
                    # Skip entire comment lines immediately
                    if line_stripped.startswith(("//", "#", "/*", "*/", "*")):
                        continue
                    
                    # Check for false positives
                    if self._is_false_positive(line_content, match.group(0), start_offset, line_start):
                        continue
                    
                    findings.append({
                        "line_number": line_number,
                        "line_content": line_content.strip(),
                        "matched_text": match.group(0),
                        "element_name": element["name"],
                        "element_category": element["category"],
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
                       exclude_dirs: Optional[set] = None,
                       progress_callback: Optional[Callable[[int, int, str], None]] = None) -> List[Dict[str, Any]]:
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
        allowed_extensions = self._normalize_extensions(extensions) if extensions is not None else self.DEFAULT_CODE_EXTENSIONS
        
        files_to_scan = []
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
            
            for file in files:
                if file.startswith('.') or file in exclude_files:
                    continue
                
                file_ext = Path(file).suffix.lower()

                if file_ext in exclude_exts:
                    continue
                    
                if file_ext not in allowed_extensions:
                    continue
                    
                files_to_scan.append(os.path.join(root, file))
        
        all_findings = []
        total_files = len(files_to_scan)
        
        # Sequential scanning to avoid Windows multiprocessing issues
        # For better performance on large codebases, consider using ThreadPoolExecutor
        if not self.data_elements:
            self._load_data_elements()
            
        for index, file_path in enumerate(files_to_scan, 1):
            if progress_callback:
                try:
                    progress_callback(index, total_files, file_path)
                except Exception:
                    # Don't break scanning if progress callback fails
                    pass
            
            try:
                file_findings = self.scan_file(file_path)
                all_findings.extend(file_findings)
            except Exception as e:
                print(f"\nError processing {file_path}: {e}")
        
        return all_findings

    @staticmethod
    def _normalize_extensions(extensions: List[str]) -> set:
        """Normalize extension values to lowercase with a leading dot."""
        normalized = set()
        for ext in extensions:
            if not ext:
                continue
            candidate = ext.strip().lower()
            if not candidate:
                continue
            if not candidate.startswith('.'):
                candidate = f'.{candidate}'
            normalized.add(candidate)
        return normalized
    
    def generate_report(self, findings: List[Dict[str, Any]], duration: Optional[float] = None, report_id: Optional[str] = None, directory_scanned: Optional[str] = None) -> str:
        """Generate formatted text report from findings."""
        if not findings:
            return "truconsent (truconsent.io)\n\ntruscanner Report\n\nNo data elements found."
        
        lines = []
        
        # Header
        lines.append("truconsent (truconsent.io)")
        lines.append("")
        lines.append("truscanner Report")
        lines.append("")
        
        # Scan Report ID
        if report_id:
            lines.append(f"Scan Report ID: {report_id}")
            lines.append("")
        
        # Summary
        lines.append("Summary")
        lines.append("-" * 80)
        lines.append(f"Total Findings: {len(findings)}")
        if duration is not None:
            lines.append(f"Time Taken: {duration:.2f} seconds")
        lines.append("")
        
        # Summary by Category
        category_details = defaultdict(lambda: defaultdict(int))
        for f in findings:
            category_details[f["element_category"]][f["element_name"]] += 1
        
        lines.append("Summary by Category")
        lines.append("-" * 80)
        for category, elements in sorted(category_details.items(), key=lambda x: sum(x[1].values()), reverse=True):
            total_count = sum(elements.values())
            distinct_count = len(elements)
            lines.append(f"\n{category}")
            lines.append(f"  Total: {total_count} ({distinct_count} distinctive elements)")
            for name, count in sorted(elements.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"    - {name}: {count}")
        lines.append("")
        lines.append("-" * 80)
        lines.append("")
        
        # Group by file and collect unique element names
        by_file = defaultdict(lambda: {"findings": [], "elements": set()})
        for f in findings:
            filename = f.get("filename", "Unknown")
            by_file[filename]["findings"].append(f)
            by_file[filename]["elements"].add(f.get("element_name", "Unknown"))
        
        # Create table
        lines.append("Tables")
        lines.append("-" * 80)
        lines.append(f"{'S.No':<8} {'File Path':<50} {'Total No. Data Element':<25} {'Data Elements'}")
        lines.append("-" * 80)
        
        # Sort files for consistent ordering
        sorted_files = sorted(by_file.items())
        for idx, (filename, file_data) in enumerate(sorted_files, 1):
            total_elements = len(file_data["elements"])
            # Format elements as pills: [Element1] [Element2] [Element3]
            element_pills = " ".join(f"[{elem}]" for elem in sorted(file_data["elements"]))
            # Truncate element pills if too long
            if len(element_pills) > 100:
                element_pills = element_pills[:97] + "..."
            # Strip directory prefix from filename
            display_filename = self._strip_directory_prefix(filename, directory_scanned)
            # Truncate filename if too long
            if len(display_filename) > 50:
                display_filename = display_filename[:47] + "..."
            lines.append(f"{idx:<8} {display_filename:<50} {total_elements:<25} {element_pills}")
        
        lines.append("-" * 80)
        lines.append("")
        
        # Findings (detailed)
        lines.append("Findings")
        lines.append("-" * 80)
        
        for filename, file_data in sorted_files:
            # Strip directory prefix from filename in findings section
            display_filename = self._strip_directory_prefix(filename, directory_scanned)
            lines.append(f"\nFile: {display_filename}")
            lines.append(f"Found {len(file_data['findings'])} data element(s)")
            lines.append("")
            
            for finding in file_data["findings"]:
                lines.extend([
                    f"  Line {finding.get('line_number', 'Unknown')}: {finding.get('element_name', 'Unknown')}",
                    f"    Category: {finding.get('element_category', 'Unknown')}",
                    f"    Matched: {finding.get('matched_text', 'N/A')}",
                    f"    Context: {str(finding.get('line_content', ''))[:100]}",
                    f"    Detected By: {finding.get('source', 'Regex')}"
                ])
                
                if finding.get("tags"):
                    tags = ", ".join(f"{k}: {v}" for k, v in finding["tags"].items())
                    lines.append(f"    Tags: {tags}")
                
                lines.append("")
            
            lines.append("-" * 80)
        
        return "\n".join(lines)
    
    def generate_markdown_report(self, findings: List[Dict[str, Any]], duration: Optional[float] = None, report_id: Optional[str] = None, directory_scanned: Optional[str] = None) -> str:
        """Generate formatted markdown report from findings."""
        if not findings:
            return "truconsent (truconsent.io)\n\n# truscanner Report\n\nNo data elements found."
        
        lines = []
        
        # Header
        lines.append("truconsent (truconsent.io)")
        lines.append("")
        lines.append("# truscanner Report")
        lines.append("")
        
        # Scan Report ID
        if report_id:
            lines.append(f"**Scan Report ID:** {report_id}")
            lines.append("")
        
        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Total Findings:** {len(findings)}")
        if duration is not None:
            lines.append(f"- **Time Taken:** {duration:.2f} seconds")
        if directory_scanned:
            lines.append(f"- **Directory Scanned:** {directory_scanned}")
        lines.append("")
        
        # Summary by Category
        category_details = defaultdict(lambda: defaultdict(int))
        for f in findings:
            category_details[f["element_category"]][f["element_name"]] += 1
        
        lines.append("## Summary by Category")
        lines.append("")
        for category, elements in sorted(category_details.items(), key=lambda x: sum(x[1].values()), reverse=True):
            total_count = sum(elements.values())
            distinct_count = len(elements)
            lines.append(f"### {category}")
            lines.append("")
            lines.append(f"- **Total:** {total_count} ({distinct_count} distinctive elements)")
            lines.append("")
            for name, count in sorted(elements.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  - {name}: {count}")
            lines.append("")
        
        # Group by file and collect unique element names
        by_file = defaultdict(lambda: {"findings": [], "elements": set()})
        for f in findings:
            filename = f.get("filename", "Unknown")
            by_file[filename]["findings"].append(f)
            by_file[filename]["elements"].add(f.get("element_name", "Unknown"))
        
        # Create markdown table
        lines.append("## Tables")
        lines.append("")
        lines.append("| S.No | File Path | Total No. Data Element | Data Elements |")
        lines.append("|------|-----------|------------------------|----------------|")
        
        # Sort files for consistent ordering
        sorted_files = sorted(by_file.items())
        for idx, (filename, file_data) in enumerate(sorted_files, 1):
            total_elements = len(file_data["elements"])
            # Format elements as pills: `Element1` `Element2` `Element3`
            element_pills = " ".join(f"`{elem}`" for elem in sorted(file_data["elements"]))
            # Truncate element pills if too long for table
            if len(element_pills) > 200:
                element_pills = element_pills[:197] + "..."
            # Strip directory prefix from filename
            display_filename = self._strip_directory_prefix(filename, directory_scanned)
            # Escape pipe characters in markdown
            element_pills = element_pills.replace("|", "\\|")
            filename_escaped = display_filename.replace("|", "\\|")
            lines.append(f"| {idx} | `{filename_escaped}` | {total_elements} | {element_pills} |")
        
        lines.append("")
        
        # Findings (detailed)
        lines.append("## Findings")
        lines.append("")
        
        for filename, file_data in sorted_files:
            # Strip directory prefix from filename in findings section
            display_filename = self._strip_directory_prefix(filename, directory_scanned)
            lines.append(f"### File: `{display_filename}`")
            lines.append("")
            lines.append(f"**Found {len(file_data['findings'])} data element(s)**")
            lines.append("")
            
            for finding in file_data["findings"]:
                lines.append(f"#### Line {finding.get('line_number', 'Unknown')}: {finding.get('element_name', 'Unknown')}")
                lines.append("")
                lines.append(f"- **Category:** {finding.get('element_category', 'Unknown')}")
                lines.append(f"- **Matched:** `{finding.get('matched_text', 'N/A')}`")
                lines.append(f"- **Context:** `{str(finding.get('line_content', ''))[:100]}`")
                lines.append(f"- **Detected By:** {finding.get('source', 'Regex')}")
                
                if finding.get("tags"):
                    tags = ", ".join(f"{k}: {v}" for k, v in finding["tags"].items())
                    lines.append(f"- **Tags:** {tags}")
                
                lines.append("")
            
            lines.append("---")
            lines.append("")
        
        return "\n".join(lines)
    
    def generate_json_report(self, findings: List[Dict[str, Any]], duration: Optional[float] = None, report_id: Optional[str] = None, directory_scanned: Optional[str] = None) -> Dict[str, Any]:
        """Generate JSON report with metadata."""
        from datetime import datetime
        
        report = {
            "scan_report_id": report_id or "",
            "timestamp": datetime.now().isoformat(),
            "directory_scanned": directory_scanned or "",
            "total_findings": len(findings),
            "scan_duration_seconds": duration,
            "findings": findings
        }
        
        return report


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
                        "tags": element.get("tags", {}),
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
