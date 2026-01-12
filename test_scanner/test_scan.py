import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from truscanner.src.regex_scanner import RegexScanner

scanner = RegexScanner()
results = scanner.scan_directory('test_scanner')

print(f"Found {len(results)} results\n")
print("=" * 80)

for r in results:
    print(f"Line {r['line_number']}: {r['element_name']}")
    print(f"  Category: {r['element_category']}")
    print(f"  Matched: {r['matched_text']}")
    print(f"  Context: {r['line_content'][:80]}")
    print()

