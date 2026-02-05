from typing import List, Dict, Any, Optional, Set
import re
import json
import concurrent.futures
from pathlib import Path
from .adapters.base import DatabaseAdapter
try:
    # When running as truscanner.database.db_scanner
    from ..regex_scanner import RegexScanner
except (ImportError, ValueError):
    # When running tests where src is in path (database is top-level)
    from regex_scanner import RegexScanner

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
        # Initialize regex scanner for content scanning (using standard patterns)
        self.regex_scanner = RegexScanner(data_elements_dir, load_immediately=True)
    
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

    def scan_table_content(self, adapter: DatabaseAdapter, table: str, schema: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Scan sample data from a table for PII."""
        findings = []
        try:
            # Get sample data
            rows = adapter.get_sample_data(table, limit=limit, schema=schema)
            if not rows:
                return []
            
            # We want to scan values. To be efficient and reuse RegexScanner, 
            # we can convert row values to a string representation or scan individually.
            # Scanning per-value allows us to pinpoint the column.
            
            # Optimization: Concatenate all values for a column and scan at once? 
            # Or just scan each value? 
            # Let's scan each value to be safe and accurate about which column it came from.
            
            # Actually, RegexScanner.scan_text is optimized.
            # But we want to know WHICH column the PII was found in.
            
            for row in rows:
                for col_name, val in row.items():
                    if val is None:
                        continue
                    
                    val_str = str(val)
                    # Skip short values / booleans / numbers to reduce noise?
                    if len(val_str) < 4: 
                        continue
                        
                    # Use RegexScanner to scan this specific value
                    # We pass context as table.column
                    val_findings = self.regex_scanner.scan_text(val_str)
                    
                    for f in val_findings:
                        # Add metadata
                        findings.append({
                            "schema_name": schema if schema else "default",
                            "table_name": table,
                            "column_name": col_name,
                            "column_type": "Unknown (Content)", # We could look up type if needed
                            "element_name": f["element_name"],
                            "element_category": f["element_category"],
                            "matched_text": f["matched_text"], # This is the actual PII value!
                            "source": "Content", # Differentiate from Metadata
                            "tags": f.get("tags", {})
                        })
                        
            # Deduplicate findings per column? 
            # If we find 50 emails in "email_address" column, we only need to report it once per column?
            # Or maybe report count?
            # Report generator aggregates by counting.
            # But for the "findings" list, let's limit to unique (element_name, column_name) tuples to avoid flooding report with 50 emails.
            
            unique_findings = {}
            for f in findings:
                key = (f["column_name"], f["element_name"])
                if key not in unique_findings:
                    unique_findings[key] = f
            
            return list(unique_findings.values())
            
        except Exception as e:
            print(f"  Warning: Error scanning content for table {table}: {e}")
            return []

    def _identify_user_id_column(self, table_name: str, columns: List[Dict[str, Any]]) -> Optional[str]:
        """Identify the user ID column in a table using heuristics."""
        col_names = [c['name'].lower() for c in columns]
        col_name_map = {c['name'].lower(): c['name'] for c in columns}
        
        # Priority 1: If table is 'users' or 'user', look for 'id'
        if table_name.lower() in ('users', 'user'):
            if 'id' in col_names:
                return col_name_map['id']
        
        # Priority 2: Exact matches
        user_id_patterns = ['user_id', 'userid', 'customer_id', 'customerid', 
                           'member_id', 'memberid', 'account_id', 'accountid']
        for pattern in user_id_patterns:
            if pattern in col_names:
                return col_name_map[pattern]
        
        # Priority 3: Suffix matches like xxx_user_id
        for col in col_names:
            if col.endswith('_user_id') or col.endswith('_customer_id'):
                return col_name_map[col]
        
        return None

    def scan_user_data_map(self, adapter: DatabaseAdapter) -> Dict[str, Dict[str, Set[str]]]:
        """
        Scan database and create a map of user_id -> {table.column: set(element_names)}.
        Returns: {user_id: {"schema.table.column": {"Email Address", ...}}}
        """
        user_data_map: Dict[str, Dict[str, Set[str]]] = {}
        
        try:
            schemas = adapter.get_schemas()
            if not schemas:
                schemas = [None]
            
            for schema in schemas:
                schema_display = schema if schema else "default"
                
                try:
                    tables = adapter.get_tables(schema=schema)
                except Exception:
                    continue
                
                for table in tables:
                    try:
                        columns = adapter.get_columns(table, schema=schema)
                    except Exception:
                        continue
                    
                    user_id_col = self._identify_user_id_column(table, columns)
                    if not user_id_col:
                        continue  # Skip tables without identifiable user ID
                    
                    print(f"  Mapping users in {schema_display}.{table} (user_id column: {user_id_col})")
                    
                    # Fetch ALL rows (no limit)
                    try:
                        rows = adapter.get_sample_data(table, limit=10000, schema=schema)  # High limit for all users
                    except Exception as e:
                        print(f"    Warning: Could not fetch data from {table}: {e}")
                        continue
                    
                    if not rows:
                        continue
                    
                    for row in rows:
                        user_id = row.get(user_id_col)
                        if user_id is None:
                            continue
                        user_id_str = str(user_id)
                        
                        if user_id_str not in user_data_map:
                            user_data_map[user_id_str] = {}
                        
                        # Scan each column value for PII
                        for col_name, val in row.items():
                            if col_name == user_id_col or val is None:
                                continue
                            
                            val_str = str(val)
                            if len(val_str) < 4:
                                continue
                            
                            # Check if column name itself matches PII (metadata)
                            col_matches = self.scan_column_name(col_name)
                            
                            # Check if value matches PII (content)
                            val_matches = self.regex_scanner.scan_text(val_str)
                            
                            all_elements = set()
                            for m in col_matches:
                                all_elements.add(m['element_name'])
                            for m in val_matches:
                                all_elements.add(m['element_name'])
                            
                            if all_elements:
                                location_key = f"{schema_display}.{table}.{col_name}"
                                if location_key not in user_data_map[user_id_str]:
                                    user_data_map[user_id_str][location_key] = set()
                                user_data_map[user_id_str][location_key].update(all_elements)
                                
        except Exception as e:
            print(f"Error during user data mapping: {e}")
        
        return user_data_map

    def scan_database(self, adapter: DatabaseAdapter) -> tuple[List[Dict[str, Any]], Dict[str, int], Dict[str, Dict[str, Set[str]]]]:
        """Scan the entire database schema. returns (findings, stats, user_data_map)"""
        all_findings = []
        stats = {
            "schemas_scanned": 0,
            "tables_scanned": 0,
            "columns_scanned": 0
        }
        
        try:
            # 1. Get all schemas
            print("Fetching schemas...")
            schemas = adapter.get_schemas()
            if not schemas:
                schemas = [None] # Default schema checking if get_schemas not supported/empty
            
            print(f"Found {len(schemas)} schemas: {schemas}")
            stats["schemas_scanned"] = len(schemas)
            
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
                        stats["columns_scanned"] += len(columns)
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

                    # Content Scanning
                    content_findings = self.scan_table_content(adapter, table, schema=schema)
                    if content_findings:
                         print(f"  Found {len(content_findings)} PII elements in content for {table}")
                         all_findings.extend(content_findings)
            
            stats["tables_scanned"] = total_tables
            
            print(f"Scanned {total_tables} tables.")
            
        except Exception as e:
            print(f"Error during database scan: {e}")
        
        # User Data Mapping
        print("\nBuilding User Data Map...")
        user_data_map = self.scan_user_data_map(adapter)
        print(f"Mapped {len(user_data_map)} unique users.")
            
        return all_findings, stats, user_data_map
