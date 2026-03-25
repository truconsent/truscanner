"""LLM response parsing utilities for truscanner.

Responsible for extracting, validating, and normalising the JSON output returned
by any AI provider into the canonical finding dict format used throughout the
codebase.
"""

import json
import re
from typing import Any, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Line-number helpers
# ---------------------------------------------------------------------------

def coerce_line_number(value: Any) -> int:
    """Parse a positive integer line number from varied model output types."""
    if isinstance(value, int):
        return value if value > 0 else 0
    if isinstance(value, float):
        return int(value) if value > 0 else 0
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        if match:
            return int(match.group(0))
    return 0


def line_number_from_prefix(text: str) -> int:
    """Read a line number from a leading prefix like ``L42:`` or ``42 -``."""
    if not isinstance(text, str):
        return 0
    match = re.match(r"^\s*L?(\d+)\s*[:|-]", text)
    if match:
        return int(match.group(1))
    return 0


def strip_line_prefix(text: str) -> str:
    """Drop leading line-number markers like ``L42:`` from a content string."""
    if not isinstance(text, str):
        return ""
    return re.sub(r"^\s*L?\d+\s*[:|-]\s*", "", text).strip()


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

def extract_json_payload(content: str) -> Optional[Any]:
    """Extract the first valid JSON payload from *content* with basic sanitation.

    Handles common LLM quirks such as:
    - Markdown code fences (```json ... ```)
    - Trailing commas before closing braces/brackets
    - Leading prose before the JSON object
    """
    if not content:
        return None

    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.IGNORECASE).strip()

    decoder = json.JSONDecoder()
    candidates = [cleaned]

    first_object = cleaned.find("{")
    first_list = cleaned.find("[")
    starts = [idx for idx in (first_object, first_list) if idx != -1]
    if starts:
        candidates.append(cleaned[min(starts):].strip())

    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        try:
            payload, _ = decoder.raw_decode(candidate)
            return payload
        except json.JSONDecodeError:
            pass
        # Fix trailing commas and retry
        sanitized = re.sub(r",(\s*[}\]])", r"\1", candidate)
        try:
            return json.loads(sanitized)
        except json.JSONDecodeError:
            continue

    return None


# ---------------------------------------------------------------------------
# Full response parser
# ---------------------------------------------------------------------------

def parse_llm_response(
    content: str,
    filepath: str,
    selected_model: str,
    file_lines: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Parse the raw JSON text returned by an LLM into a list of finding dicts.

    Args:
        content: Raw text response from the LLM.
        filepath: Original file path (stored in each finding's ``filename`` key).
        selected_model: Model identifier string, embedded in the ``source`` field.
        file_lines: Optional list of source-file lines used to resolve line
            numbers and fill in ``line_content`` from the real file.

    Returns:
        A (possibly empty) list of validated finding dicts. Findings with a
        missing or empty ``element_name`` are silently dropped.
    """
    try:
        raw_findings = extract_json_payload(content)
        if raw_findings is None:
            if content.strip():
                logger.warning("No JSON found in LLM response for {}", filepath)
            return []

        findings_list: Any = []
        if isinstance(raw_findings, list):
            findings_list = raw_findings
        elif isinstance(raw_findings, dict):
            findings_list = raw_findings.get(
                "findings",
                raw_findings.get("data_elements", raw_findings.get("data", [])),
            )
            if not findings_list and {"line_number", "element_name"} <= set(raw_findings.keys()):
                findings_list = [raw_findings]

        if isinstance(findings_list, dict):
            findings_list = [findings_list]
        if not isinstance(findings_list, list):
            return []

        validated: List[Dict[str, Any]] = []
        for finding in findings_list:
            if not isinstance(finding, dict):
                continue

            # element_name is required — skip vague/empty findings.
            element_name = str(
                finding.get("element_name", finding.get("type", "")) or ""
            ).strip()
            if not element_name:
                logger.debug("Skipping finding with missing element_name in {}", filepath)
                continue

            raw_line_content = str(finding.get("line_content", finding.get("context", "")) or "")

            line_number = coerce_line_number(finding.get("line_number"))
            if line_number <= 0:
                line_number = line_number_from_prefix(raw_line_content)

            cleaned_line_content = strip_line_prefix(raw_line_content)

            if file_lines and line_number <= 0 and cleaned_line_content:
                # Best-effort lookup when the model omitted line numbers.
                for idx, line in enumerate(file_lines, 1):
                    if line.strip() == cleaned_line_content:
                        line_number = idx
                        break

            if file_lines and 0 < line_number <= len(file_lines):
                cleaned_line_content = file_lines[line_number - 1].strip() or cleaned_line_content

            matched_text = (
                finding.get("matched_text")
                or finding.get("matched")
                or finding.get("value")
                or ""
            )

            validated.append({
                "line_number": line_number,
                "line_content": cleaned_line_content,
                "matched_text": matched_text,
                "element_name": element_name,
                "element_category": str(
                    finding.get("element_category", finding.get("category", "Privacy")) or "Privacy"
                ).strip(),
                "reason": finding.get("reason", ""),
                "filename": filepath,
                "source": f"LLM ({selected_model})",
            })

        return validated

    except Exception as e:
        logger.error("Error parsing LLM response for {}: {}", filepath, e)
        return []
