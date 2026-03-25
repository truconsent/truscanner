import os
import re
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from collections import defaultdict
import bisect

from loguru import logger


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

        file_path_norm = os.path.normpath(file_path)
        base_dir_norm = os.path.normpath(base_directory)

        if file_path_norm.startswith(base_dir_norm):
            relative = file_path_norm[len(base_dir_norm):]
            if not relative.startswith(os.sep) and not relative.startswith('/'):
                relative = os.sep + relative
            return relative

        return file_path

    DEFAULT_EXCLUDE_FILES = {
        'tsconfig.node.json', 'tsconfig.app.json', 'tsconfig.json',
        'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'bun.lock',
        'tailwind.config.ts', 'tailwind.config.js', 'package.json',
        '.DS_Store', 'vite.config.ts', 'vite.config.js', 'eslint.config.js',
    }
    DEFAULT_EXCLUDE_EXTENSIONS = {
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.pdf',
        '.zip', '.gz', '.tar', '.log', '.css', '.db', '.sqlite',
        '.sqlite3', '.bin', '.exe', '.dll', '.so', '.dylib',
    }

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
            logger.error("Error loading {}: {}", json_file, e)

    def _is_false_positive(self, line_content: str, matched_text: str, match_start: int, line_start: int) -> bool:
        """Check if a match is likely a false positive."""
        line_lower = line_content.lower()
        matched_lower = matched_text.lower().strip()
        line_stripped = line_content.strip()

        # Skip entire lines that are comments (start with //, #, /*, or *)
        if line_stripped.startswith(("//", "#", "/*", "*/", "*")):
            return True

        # Skip matches in single-line comments (both // and #)
        comment_idx = line_content.find("//")
        if comment_idx == -1:
            comment_idx = line_content.find("#")
        if comment_idx != -1:
            match_pos = match_start - line_start
            if match_pos > comment_idx:
                return True
            if comment_idx < match_pos and not line_content[:comment_idx].strip():
                return True

        # Skip matches in multi-line comments (/* ... */)
        before_match = line_content[:match_start - line_start]
        if "/*" in before_match:
            comment_start = before_match.rfind("/*")
            comment_end = line_content.find("*/", comment_start)
            if comment_end == -1 or comment_end > match_start - line_start:
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

        # Skip if match is in a string that's clearly not personal data
        if re.search(r'["\']\s*(email|phone|name|address)\s*(field|column|attribute|property)', line_lower):
            return True

        # Skip SQL field names (SELECT, INSERT, UPDATE statements) - field names only
        if re.search(r'\b(SELECT|INSERT\s+INTO|UPDATE\s+\w+\s+SET)\s+', line_content, re.IGNORECASE):
            if '"' in line_content or "'" in line_content:
                quote_start = max(line_content.rfind('"', 0, match_pos), line_content.rfind("'", 0, match_pos))
                quote_end = min(
                    line_content.find('"', match_pos) if line_content.find('"', match_pos) != -1 else len(line_content),
                    line_content.find("'", match_pos) if line_content.find("'", match_pos) != -1 else len(line_content)
                )
                if quote_start != -1 and quote_end > match_pos:
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
            if not re.search(r'email\s*[:=]\s*["\']?[^"\']*@', line_content, re.IGNORECASE):
                return True

        # Only match actual phone numbers (with digits), not just the word "phone"
        if matched_lower in ["phone", "mobile"] and not re.search(r'\d{6,}', line_content):
            if not re.search(r'(phone|mobile)\s*[:=]\s*["\']?[^"\']*\d{6,}', line_content, re.IGNORECASE):
                return True

        # Skip variable declarations without actual values (just variable names)
        if re.search(r'\b(const|let|var)\s+' + re.escape(matched_text) + r'\s*[;,]', line_content, re.IGNORECASE):
            return True

        # Only match if there's actual data — skip assignments without a value
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

        lines = None  # Lazy split if needed
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
            logger.error("Error scanning {}: {}", filepath, e)
            return []

    def scan_directory(
        self,
        directory: str,
        extensions: Optional[List[str]] = None,
        exclude_dirs: Optional[set] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Recursively scan directory or file for data elements using parallel I/O."""
        path = Path(directory)

        if not path.exists():
            logger.error("Path not found: {}", directory)
            return []

        if path.is_file():
            return self.scan_file(str(path))

        effective_exclude_dirs = exclude_dirs or self.DEFAULT_EXCLUDE_DIRS
        exclude_files = self.DEFAULT_EXCLUDE_FILES
        exclude_exts = self.DEFAULT_EXCLUDE_EXTENSIONS
        allowed_extensions = (
            self._normalize_extensions(extensions)
            if extensions is not None
            else self.DEFAULT_CODE_EXTENSIONS
        )

        files_to_scan = []
        # followlinks=False (default) prevents symlink loops
        for root, dirs, files in os.walk(path, followlinks=False):
            dirs[:] = [d for d in dirs if d not in effective_exclude_dirs and not d.startswith('.')]

            for file in files:
                if file.startswith('.') or file in exclude_files:
                    continue

                file_ext = Path(file).suffix.lower()
                if file_ext in exclude_exts:
                    continue
                if file_ext not in allowed_extensions:
                    continue

                files_to_scan.append(os.path.join(root, file))

        if not self.data_elements:
            self._load_data_elements()

        all_findings = []
        total_files = len(files_to_scan)
        completed = 0
        lock = threading.Lock()

        max_workers = min(8, (os.cpu_count() or 4))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_path = {executor.submit(self.scan_file, fp): fp for fp in files_to_scan}
            for future in as_completed(future_to_path):
                fp = future_to_path[future]
                with lock:
                    completed += 1
                    current = completed

                if progress_callback:
                    try:
                        progress_callback(current, total_files, fp)
                    except Exception:
                        pass

                try:
                    all_findings.extend(future.result())
                except Exception as e:
                    logger.error("Error processing {}: {}", fp, e)

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

    def generate_report(
        self,
        findings: List[Dict[str, Any]],
        duration: Optional[float] = None,
        report_id: Optional[str] = None,
        directory_scanned: Optional[str] = None,
    ) -> str:
        """Generate formatted text report from findings."""
        if not self.data_elements:
            self._load_data_elements()
        configured_elements = len(self.data_elements)
        distinct_detected_elements = len(
            {
                finding.get("element_name")
                for finding in findings
                if finding.get("element_name")
            }
        )

        if not findings:
            lines = [
                "truconsent (truconsent.io)",
                "",
                "truscanner Report",
                "",
                "Summary",
                "-" * 80,
                f"Configured Data Elements: {configured_elements}",
                "Distinct Detected Elements: 0",
                "Total Findings: 0",
                "",
                "No data elements found.",
            ]
            return "\n".join(lines)

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
        lines.append(f"Configured Data Elements: {configured_elements}")
        lines.append(f"Distinct Detected Elements: {distinct_detected_elements}")
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

        sorted_files = sorted(by_file.items())
        for idx, (filename, file_data) in enumerate(sorted_files, 1):
            total_elements = len(file_data["elements"])
            element_pills = " ".join(f"[{elem}]" for elem in sorted(file_data["elements"]))
            if len(element_pills) > 100:
                element_pills = element_pills[:97] + "..."
            display_filename = self._strip_directory_prefix(filename, directory_scanned)
            if len(display_filename) > 50:
                display_filename = display_filename[:47] + "..."
            lines.append(f"{idx:<8} {display_filename:<50} {total_elements:<25} {element_pills}")

        lines.append("-" * 80)
        lines.append("")

        # Findings (detailed)
        lines.append("Findings")
        lines.append("-" * 80)

        for filename, file_data in sorted_files:
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

    def generate_markdown_report(
        self,
        findings: List[Dict[str, Any]],
        duration: Optional[float] = None,
        report_id: Optional[str] = None,
        directory_scanned: Optional[str] = None,
    ) -> str:
        """Generate formatted markdown report from findings."""
        if not self.data_elements:
            self._load_data_elements()
        configured_elements = len(self.data_elements)
        distinct_detected_elements = len(
            {
                finding.get("element_name")
                for finding in findings
                if finding.get("element_name")
            }
        )

        if not findings:
            lines = [
                "truconsent (truconsent.io)",
                "",
                "# truscanner Report",
                "",
                "## Summary",
                "",
                f"- **Configured Data Elements:** {configured_elements}",
                "- **Distinct Detected Elements:** 0",
                "- **Total Findings:** 0",
                "",
                "No data elements found.",
            ]
            return "\n".join(lines)

        lines = []

        # Header
        lines.append("truconsent (truconsent.io)")
        lines.append("")
        lines.append("# truscanner Report")
        lines.append("")

        if report_id:
            lines.append(f"**Scan Report ID:** {report_id}")
            lines.append("")

        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Configured Data Elements:** {configured_elements}")
        lines.append(f"- **Distinct Detected Elements:** {distinct_detected_elements}")
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

        lines.append("## Tables")
        lines.append("")
        lines.append("| S.No | File Path | Total No. Data Element | Data Elements |")
        lines.append("|------|-----------|------------------------|----------------|")

        sorted_files = sorted(by_file.items())
        for idx, (filename, file_data) in enumerate(sorted_files, 1):
            total_elements = len(file_data["elements"])
            element_pills = " ".join(f"`{elem}`" for elem in sorted(file_data["elements"]))
            if len(element_pills) > 200:
                element_pills = element_pills[:197] + "..."
            display_filename = self._strip_directory_prefix(filename, directory_scanned)
            element_pills = element_pills.replace("|", "\\|")
            filename_escaped = display_filename.replace("|", "\\|")
            lines.append(f"| {idx} | `{filename_escaped}` | {total_elements} | {element_pills} |")

        lines.append("")

        lines.append("## Findings")
        lines.append("")

        for filename, file_data in sorted_files:
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

    def generate_json_report(
        self,
        findings: List[Dict[str, Any]],
        duration: Optional[float] = None,
        report_id: Optional[str] = None,
        directory_scanned: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate JSON report with metadata."""
        from datetime import datetime

        if not self.data_elements:
            self._load_data_elements()
        configured_elements = len(self.data_elements)
        distinct_detected_elements = len(
            {
                finding.get("element_name")
                for finding in findings
                if finding.get("element_name")
            }
        )

        return {
            "scan_report_id": report_id or "",
            "timestamp": datetime.now().isoformat(),
            "directory_scanned": directory_scanned or "",
            "configured_data_elements": configured_elements,
            "distinct_detected_elements": distinct_detected_elements,
            "total_findings": len(findings),
            "scan_duration_seconds": duration,
            "findings": findings,
        }


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


if __name__ == "__main__":
    main()
