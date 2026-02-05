
import unittest
from unittest.mock import MagicMock, patch
import sys
import os
from pathlib import Path

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from database.db_scanner import DatabaseSchemaScanner
from database.adapters.base import DatabaseAdapter

class TestContentScanning(unittest.TestCase):
    def setUp(self):
        # Create a mock adapter
        self.mock_adapter = MagicMock(spec=DatabaseAdapter)
        self.scanner = DatabaseSchemaScanner()
        
        # Mock regex scanner to return predictable results
        self.scanner.regex_scanner = MagicMock()
        self.scanner.regex_scanner.scan_text.side_effect = self._mock_scan_text

    def _mock_scan_text(self, text):
        if "test@example.com" in text:
            return [{
                "element_name": "Email Address",
                "element_category": "PII",
                "matched_text": "test@example.com",
                "tags": {}
            }]
        return []

    def test_scan_table_content_finding(self):
        """Test that scan_table_content finds PII in sample data."""
        # Setup mock data
        self.mock_adapter.get_sample_data.return_value = [
            {"id": 1, "data": "test@example.com", "other": "safe"},
            {"id": 2, "data": "nothing", "other": "none"}
        ]
        
        findings = self.scanner.scan_table_content(self.mock_adapter, "users")
        
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["column_name"], "data")
        self.assertEqual(findings[0]["element_name"], "Email Address")
        self.assertEqual(findings[0]["source"], "Content")

    def test_scan_database_integration(self):
        """Test that scan_database calls content scanning and aggregates findings."""
        # Setup schema
        self.mock_adapter.get_schemas.return_value = ["public"]
        self.mock_adapter.get_tables.return_value = ["users"]
        self.mock_adapter.get_columns.return_value = [
            {"name": "id", "type": "int"},
            {"name": "data", "type": "text"}
        ]
        
        # Setup content data
        self.mock_adapter.get_sample_data.return_value = [
            {"id": 1, "data": "test@example.com"}
        ]
        
        # Mock scan_column_name to return nothing to ensure we're testing content scan
        self.scanner.scan_column_name = MagicMock(return_value=[])
        
        findings, stats = self.scanner.scan_database(self.mock_adapter)
        
        # Should find at least the content finding
        # (scan_database might aggregate or filter, let's check)
        
        content_findings = [f for f in findings if f.get("source") == "Content"]
        self.assertEqual(len(content_findings), 1)
        self.assertEqual(content_findings[0]["table_name"], "users")
        self.assertEqual(content_findings[0]["element_name"], "Email Address")

if __name__ == '__main__':
    unittest.main()
