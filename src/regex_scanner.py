import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict


class RegexScanner:
    """Scanner that uses regex patterns from JSON files to identify privacy data elements."""
    
    DEFAULT_EXCLUDE_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build', '.next', '.cache'}
    SENSITIVITY_EMOJI = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
    
    def __init__(self, data_elements_dir: Optional[str] = None):
        """Initialize scanner with data element patterns from JSON files."""
        if data_elements_dir is None:
            data_elements_dir = Path(__file__).parent.parent / "data_elements"
        
        self.data_elements_dir = Path(data_elements_dir)
        self.data_elements = []
        self._load_data_elements()
    
    def _load_data_elements(self):
        """Load and compile regex patterns from all JSON files."""
        if not self.data_elements_dir.exists():
            print(f"Warning: Data elements directory not found: {self.data_elements_dir}")
            return
        
        for json_file in self.data_elements_dir.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                for source in data.get("sources", []):
                    compiled_patterns = []
                    for pattern in source.get("patterns", []):
                        try:
                            compiled_patterns.append(re.compile(pattern))
                        except re.error as e:
                            print(f"Warning: Invalid regex in {source['name']}: {e}")
                    
                    if compiled_patterns:
                        self.data_elements.append({
                            "name": source["name"],
                            "category": source["category"],
                            "isSensitive": source.get("isSensitive", False),
                            "sensitivity": source.get("sensitivity", "low"),
                            "patterns": compiled_patterns,
                            "tags": source.get("tags", {})
                        })
                
                print(f"Loaded {len(data.get('sources', []))} data elements from {json_file.name}")
            except Exception as e:
                print(f"Error loading {json_file}: {e}")
        
        print(f"Total data elements loaded: {len(self.data_elements)}")
    
    def scan_text(self, text: str, context: str = "") -> List[Dict[str, Any]]:
        """Scan text for data elements and return findings."""
        findings = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            for element in self.data_elements:
                for pattern in element["patterns"]:
                    if match := pattern.search(line):
                        findings.append({
                            "line_number": line_number,
                            "line_content": line.strip(),
                            "matched_text": match.group(0),
                            "element_name": element["name"],
                            "element_category": element["category"],
                            "isSensitive": element["isSensitive"],
                            "sensitivity": element["sensitivity"],
                            "tags": element["tags"],
                            "context": context,
                            "source": "Regex"
                        })
                        break  # One match per element per line
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
        """Recursively scan directory or file for data elements."""
        path = Path(directory)
        
        if not path.exists():
            print(f"Error: Path not found: {directory}")
            return []
        
        # Handle single file
        if path.is_file():
            return self.scan_file(str(path))
        
        # Handle directory
        exclude_dirs = exclude_dirs or self.DEFAULT_EXCLUDE_DIRS
        all_findings = []
        
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
            
            for file in files:
                if file.startswith('.'):
                    continue
                
                if extensions and not any(file.endswith(ext) for ext in extensions):
                    continue
                
                all_findings.extend(self.scan_file(os.path.join(root, file)))
        
        return all_findings
    
    def generate_report(self, findings: List[Dict[str, Any]]) -> str:
        """Generate formatted report from findings."""
        if not findings:
            return "No data elements found."
        
        lines = [
            "=" * 80,
            "REGEX SCANNER REPORT",
            "=" * 80,
            f"\nTotal Findings: {len(findings)}\n",
            "-" * 80
        ]
        
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
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python regex_scanner.py <directory_to_scan>")
        sys.exit(1)
    
    scanner = RegexScanner()
    findings = scanner.scan_directory(sys.argv[1])
    report = scanner.generate_report(findings)
    
    print(f"\nScanning: {sys.argv[1]}\n")
    print(report)
    
    output_file = "regex_scan_report.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n✅ Report saved to: {output_file}")


if __name__ == "__main__":
    main()
