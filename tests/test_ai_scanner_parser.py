from src.ai_scanner import AIScanner


def test_parse_llm_response_accepts_list_with_trailing_commas(tmp_path):
    scanner = AIScanner(data_elements_dir=tmp_path)
    scanner.selected_model = "qwen2.5:3b"
    content = """
Some preface text
[
  {
    "line_number": "12",
    "line_content": "email = 'john@example.com'",
    "matched_text": "john@example.com",
    "element_name": "Email Address",
    "element_category": "Contact Information",
    "reason": "Contains an email address",
  },
]
"""

    findings = scanner._parse_llm_response(content, "src/app.py")

    assert len(findings) == 1
    assert findings[0]["line_number"] == 12
    assert findings[0]["filename"] == "src/app.py"
    assert findings[0]["source"] == "LLM (qwen2.5:3b)"


def test_parse_llm_response_accepts_object_payload(tmp_path):
    scanner = AIScanner(data_elements_dir=tmp_path)
    scanner.selected_model = "gemma3:4b"
    content = """
{
  "findings": [
    {
      "line_number": 4,
      "context": "const ip = '127.0.0.1';",
      "matched": "127.0.0.1",
      "element_name": "IP Address",
      "element_category": "Digital IDs",
      "reason": "Contains an IP"
    }
  ]
}
"""

    findings = scanner._parse_llm_response(content, "src/utils.py")

    assert len(findings) == 1
    assert findings[0]["line_content"] == "const ip = '127.0.0.1';"
    assert findings[0]["matched_text"] == "127.0.0.1"
    assert findings[0]["source"] == "LLM (gemma3:4b)"


def test_parse_llm_response_returns_empty_when_no_json(tmp_path):
    scanner = AIScanner(data_elements_dir=tmp_path)
    findings = scanner._parse_llm_response("No findings in this response", "src/main.py")
    assert findings == []
