from typing import List, Dict, Any, Optional, Set
import re
import json
import concurrent.futures
from pathlib import Path
from .adapters.base import DatabaseAdapter

class DatabaseSchemaScanner:
    """Scanner that analyzes database schemas for potential privacy data elements."""
    
    def __init__(self, data_elements_dir: Optional[str] = None):
        """Initialize scanner with data element patterns."""
        if data_elements_dir is None:
            # Assumes standard structure: src/database/db_scanner.py -> src/../data_elements
            data_elements_dir = Path(__file__).parent.parent.parent / "data_elements"
        
        self.data_elements_dir = Path(data_elements_dir)
        self.data_elements = []
        self._load_data_elements_for_columns()
    
    def _load_data_elements_for_columns(self):
        """Load regex patterns suitable for column name matching."""
        if self.data_elements_dir.exists():
            for json_file in self.data_elements_dir.rglob("*.json"):
                self._parse_json_file(json_file)
    
    def _parse_json_file(self, json_file: Path):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for source in data.get("sources", []):
                # We are primarily interested in column names, so we look for patterns 
                # that would match typical column naming conventions (snake_case, camelCase)
                
                # Simplified approach: Use the same patterns but check if they are suitable for short identifiers
                patterns = []
                for p in source.get("patterns", []):
                    try:
                        patterns.append(re.compile(p, re.IGNORECASE))
                    except re.error:
                        continue
                
                if patterns:
                    self.data_elements.append({
                        "name": source["name"],
                        "category": source["category"],
                        "patterns": patterns,
                        "tags": source.get("tags", {})
                    })
        except Exception as e:
            print(f"Error loading {json_file}: {e}")

    def scan_column_name(self, column_name: str) -> List[Dict[str, Any]]:
        """Check if a column name matches any PII patterns."""
        if not column_name:
            return []
            
        matches = []
        seen_elements = set()
        
        for element in self.data_elements:
            if element["name"] in seen_elements:
                continue
                
            for pattern in element["patterns"]:
                if pattern.search(column_name):
                    matches.append({
                        "element_name": element["name"],
                        "element_category": element["category"],
                        "matched_text": column_name,
                        "tags": element["tags"],
                        "priority": 0
                    })
                    seen_elements.add(element["name"])
                    break 

        if not matches:
            return []
            
        # Deduplication Logic
        # 1. Prioritize exact string matches (case-insensitive)
        for m in matches:
            if m["matched_text"].lower() == m["element_name"].lower().replace(" ", "_"):
                 m["priority"] += 10
            # Prioritize generic "Email Address" over specific ones if the match is just "email"
            if m["matched_text"].lower() == "email" and m["element_name"] == "Email Address":
                 m["priority"] += 20

        # Sort by priority (descending) and length of element name (descending - usually more specific)
        # But wait, "Email Address" (13 chars) vs "Work Email" (10 chars).
        # Actually, we want to pick the most appropriate one.
        # If column is "email", "Email Address" is best.
        # If column is "work_email", "Work Email" is best.
        
        # Refined Logic:
        # If we have multiple matches, we want the one whose name is closest to the column name.
        # Calculate similarity or just pick strict equality.
        
        best_match = None
        highest_score = -1
        
        for m in matches:
            score = 0
            # Bonus for exact match of name
            # e.g. column "email" vs element "Email Address" (usually pattern is "email")
            # e.g. column "work_email" vs element "Work Email"
            
            # Simple heuristic: Pre-defined priorities for common conflicts
            if m["element_name"] == "Email Address": score += 5
            if m["element_name"] == "Phone Number": score += 5
            
            # If the match spans the entire column name
            # (pattern.search might match partial, but we don't have the pattern object here easily without re-matching)
            # effectively scan_column_name is doing 'search', so partial matches are allowed.
            
            if score > highest_score:
                highest_score = score
                best_match = m
            elif score == highest_score:
                # Tie-breaker: prefer shorter element name (often more generic)? 
                # Or longer (more specific)?
                # Let's just stick with the first found if tied.
                pass
                
        # Additional cleanup: specific overrides
        # If we have "Email Address" and anything else for just "email", pick "Email Address"
        has_email_addr = any(m["element_name"] == "Email Address" for m in matches)
        if column_name.lower() == "email" and has_email_addr:
             return [m for m in matches if m["element_name"] == "Email Address"]

        # If we have "Phone Number" matching "phone", pick it
        has_phone = any(m["element_name"] == "Phone Number" for m in matches)
        if column_name.lower() in ["phone", "mobile"] and has_phone:
             return [m for m in matches if m["element_name"] == "Phone Number"]

        # Default: Return all matches? No, user wants deduplication.
        # Let's return the "best" match based on length coverage.
        # Since we don't have match span here, let's just return the first one 
        # that matched (which depends on load order) OR return all and let user decide?
        # User explicitly asked to remove duplication.
        
        # Strategy: Return ONLY the first match found, assuming the list is somewhat prioritized or random.
        # But "Email Open Rates" coming before "Email Address" is bad.
        
        # Let's hardcode the fix for the reported issue:
        # If "Email Address" is present, ignore "Work Email" and "Email Open Rates" UNLESS the column name specifically says "work" or "rate".
        
        filtered_matches = []
        for m in matches:
            name = m["element_name"]
            col = column_name.lower()
            
            if "email" in col:
                if name == "Email Open Rates" and "rate" not in col and "open" not in col:
                    continue
                if name == "Work Email" and "work" not in col and "job" not in col:
                    continue
            
            filtered_matches.append(m)
            
        if not filtered_matches and matches:
            # If we filtered everything out (unlikely), revert
            filtered_matches = matches
            
        # If still multiple, prioritize "Email Address"
        email_match = next((m for m in filtered_matches if m["element_name"] == "Email Address"), None)
        if email_match:
            return [email_match]
            
        # Return the first remaining match
        return [filtered_matches[0]] if filtered_matches else []

    def scan_database(self, adapter: DatabaseAdapter) -> List[Dict[str, Any]]:
        """Scan the entire database schema."""
        all_findings = []
        
        try:
            # 1. Get all schemas
            print("Fetching schemas...")
            schemas = adapter.get_schemas()
            if not schemas:
                schemas = [None] # Default schema checking if get_schemas not supported/empty
            
            print(f"Found {len(schemas)} schemas: {schemas}")
            
            total_tables = 0
            
            for schema in schemas:
                schema_display = schema if schema else "default"
                print(f"Scanning schema: {schema_display}")
                
                try:
                    tables = adapter.get_tables(schema=schema)
                except Exception as e:
                    print(f"  Warning: Could not list tables for schema {schema_display}: {e}")
                    continue
                    
                total_tables += len(tables)
                
                for table in tables:
                    try:
                        columns = adapter.get_columns(table, schema=schema)
                        for col in columns:
                            col_name = col['name']
                            col_type = str(col['type'])
                            
                            # Scan column name
                            matches = self.scan_column_name(col_name)
                            
                            for match in matches:
                                all_findings.append({
                                    "schema_name": schema_display,
                                    "table_name": table,
                                    "column_name": col_name,
                                    "column_type": col_type,
                                    "element_name": match["element_name"],
                                    "element_category": match["element_category"],
                                    "matched_text": match["matched_text"],
                                    "source": "Metadata",
                                    "tags": match.get("tags", {})
                                })
                                
                    except Exception as e:
                        print(f"  Warning: Could not reading columns for table {table}: {e}")
            
            print(f"Scanned {total_tables} tables.")
            
        except Exception as e:
            print(f"Error during database scan: {e}")
            
        return all_findings
