import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict
import concurrent.futures
import bisect


# Global variables for workers
_worker_data_elements = []
_worker_storage_elements = []

def _worker_init(data_dir, sinks_dir):
    """Initialize worker process by loading patterns once."""
    global _worker_data_elements, _worker_storage_elements
    scanner = RegexScanner(data_dir, sinks_dir, load_immediately=True)
    _worker_data_elements = scanner.data_elements
    _worker_storage_elements = scanner.storage_elements

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
    
    def __init__(self, data_elements_dir: Optional[str] = None, sinks_dir: Optional[str] = None, load_immediately: bool = True):
        """Initialize scanner with data element patterns and storage sinks."""
        if data_elements_dir is None:
            data_elements_dir = Path(__file__).parent.parent / "data_elements"
        if sinks_dir is None:
            sinks_dir = Path(__file__).parent.parent / "sinks"
        
        self.data_elements_dir = Path(data_elements_dir)
        self.sinks_dir = Path(sinks_dir)
        self.data_elements = []
        self.storage_elements = []
        if load_immediately:
            self._load_data_elements()
    
    def _load_data_elements(self):
        """Load patterns and sinks from JSON files."""
        # 1. Load Data Elements
        if self.data_elements_dir.exists():
            for json_file in self.data_elements_dir.rglob("*.json"):
                self._parse_json_file(json_file, is_storage_file=False)
        
        # 2. Load Storage Sinks
        if self.sinks_dir.exists():
            for json_file in self.sinks_dir.rglob("*.json"):
                self._parse_json_file(json_file, is_storage_file=True)

    def _parse_json_file(self, json_file: Path, is_storage_file: bool = False):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for source in data.get("sources", []):
                compiled_patterns = []
                keywords = set()
                is_storage = (source.get("category") == "Storage Sink") or is_storage_file
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
                        "category": "Storage Sink" if is_storage else source["category"],
                        "isSensitive": source.get("isSensitive", False),
                        "sensitivity": source.get("sensitivity", "low"),
                        "patterns": compiled_patterns,
                        "keywords": list(keywords),
                        "tags": source.get("tags", {})
                    }
                    if is_storage:
                        self.storage_elements.append(element_info)
                    else:
                        self.data_elements.append(element_info)
        except Exception as e:
            print(f"Error loading {json_file}: {e}")
    
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
                    
                    findings.append({
                        "line_number": line_number,
                        "line_content": line_content.strip(),
                        "matched_text": match.group(0),
                        "element_name": element["name"],
                        "element_category": element["category"],
                        "isSensitive": element["isSensitive"],
                        "sensitivity": element["sensitivity"],
                        "tags": element["tags"],
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
    
    def generate_report(self, findings: List[Dict[str, Any]], duration: Optional[float] = None, stored_only: bool = False) -> str:
        """Generate formatted report from findings with storage awareness."""
        if stored_only:
            findings = [f for f in findings if f.get("is_stored")]
            
        if not findings:
            return "No data elements found (Stored Only: On)" if stored_only else "No data elements found."
        
        header = [
            "=" * 80,
            "REGEX SCANNER REPORT" + (" (STORED DATA ONLY)" if stored_only else ""),
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
                stored_indicator = " [🗄️ Stored]" if finding.get("is_stored") else ""
                lines.extend([
                    f"   {emoji} Line {finding['line_number']}: {finding['element_name']}{stored_indicator}",
                    f"      Category: {finding['element_category']}",
                    f"      Sensitivity: {finding['sensitivity']}",
                    f"      Matched: {finding['matched_text']}",
                    f"      Context: {finding['line_content'][:100]}"
                ])
                
                if finding.get("is_stored") and finding.get("sink_evidence"):
                    unique_evidence = []
                    seen_evidence = set()
                    for evidence in finding["sink_evidence"]:
                        # Much stricter deduplication: only show one entry per Type [Tech] per finding
                        # to keep the report compact.
                        tech_key = evidence.get("technology", "Unknown")
                        key = (evidence["type"], tech_key)
                        if key not in seen_evidence:
                            unique_evidence.append(evidence)
                            seen_evidence.add(key)
                    
                    for evidence in unique_evidence:
                        tech_info = f" [{evidence['technology'].capitalize()}]" if evidence.get('technology') and evidence['technology'] != "Unknown" else ""
                        lines.append(f"      🗄️ Stored in: {evidence['type']}{tech_info} (Evidence: {evidence['match']} at Line {evidence['line']})")
                
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
        
        # Storage Sink Summary
        sink_summary = defaultdict(int)
        for f in findings:
            if f.get("is_stored"):
                sinks = f["sink_type"].split(", ")
                for sink in sinks:
                    sink_summary[sink] += 1
        
        if sink_summary:
            lines.append("\n🗄️ STORAGE SINK SUMMARY\n")
            for sink, count in sorted(sink_summary.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"   {sink}: {count} data element(s) persisted")

        # Detailed Database Audit
        db_audit = defaultdict(list)
        for f in findings:
            if f.get("is_stored") and f.get("sink_evidence"):
                for evidence in f["sink_evidence"]:
                    if evidence.get("type") == "Database":
                        tech = evidence.get("technology", "SQL").capitalize()
                        # Deduplicate entries for this element in this file/line
                        entry = f"[{f['element_name']}] in {f['filename']} at Line {evidence['line']} ({evidence['match']})"
                        if entry not in db_audit[tech]:
                            db_audit[tech].append(entry)
        
        if db_audit:
            lines.append("\n📊 DATABASE AUDIT\n")
            for tech, entries in sorted(db_audit.items()):
                lines.append(f"   {tech}")
                for entry in sorted(entries):
                    lines.append(f"      - {entry}")

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
    global _worker_data_elements, _worker_storage_elements
    try:
        data_elements = _worker_data_elements
        storage_elements = _worker_storage_elements
        
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

        # Phase 1: Identify Storage Sinks with Evidence
        sink_evidence = []
        for sink in storage_elements:
            # Quick keyword check
            if sink.get("keywords") and not any(kw in text_lower for kw in sink["keywords"]):
                continue
            
            for pattern in sink["patterns"]:
                for match in pattern.finditer(text):
                    sink_line = bisect.bisect_right(line_starts, match.start())
                    sink_match = match.group(0).strip()
                    sink_evidence.append({
                        "type": sink["tags"].get("type", "Generic Storage"),
                        "technology": sink["tags"].get("technology", "Unknown"),
                        "match": sink_match,
                        "line": sink_line
                    })
        
        is_stored = len(sink_evidence) > 0
        sink_types = ", ".join(list(set(e["type"] for e in sink_evidence))) if is_stored else None

        # Phase 2: Identify Data Elements
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
                        "source": "Regex",
                        "is_stored": is_stored,
                        "sink_type": sink_types,
                        "sink_evidence": sink_evidence
                    }
                    findings.append(finding)
        return findings
    except Exception as e:
        print(f"Error scanning {filepath}: {e}")
        return []


if __name__ == "__main__":
    main()
