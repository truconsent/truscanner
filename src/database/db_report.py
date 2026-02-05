from typing import List, Dict, Any, Optional, Set
from collections import defaultdict
import datetime

class DatabaseReportGenerator:
    """Generates formatted reports for database scan findings."""
    
    @staticmethod
    def generate_report(findings: List[Dict[str, Any]], duration: Optional[float] = None, 
                       db_connection_info: Optional[str] = None, report_id: Optional[str] = None,
                       stats: Dict[str, int] = None,
                       user_data_map: Dict[str, Dict[str, Set[str]]] = None) -> str:
        """Generate formatted TXT report."""
        if stats is None:
            stats = {}
        if user_data_map is None:
            user_data_map = {}
            
        lines = []
        lines.append("truconsent (truconsent.io)")
        lines.append("")
        lines.append("truscanner Database Schema Report")
        if report_id:
            lines.append(f"Scan Report ID: {report_id}")
        if db_connection_info:
            lines.append(f"Database: {db_connection_info}")
        lines.append(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        # Calculate derived metrics
        unique_data_elements = len(set(f['element_name'] for f in findings)) if findings else 0
        schemas_with_pii = len(set(f['schema_name'] for f in findings)) if findings else 0
        tables_with_pii = len(set((f['schema_name'], f['table_name']) for f in findings)) if findings else 0
        columns_with_pii = len(set((f['schema_name'], f['table_name'], f['column_name']) for f in findings)) if findings else 0
        
        # Discovery Report
        lines.append("Discovery Report")
        lines.append("-" * 30)
        lines.append(f"Unique User Count:          {len(user_data_map)}") 
        lines.append(f"Unique Data Element count:  {unique_data_elements}")
        lines.append(f"Total Schema Scanned:       {stats.get('schemas_scanned', 'N/A')}")
        lines.append(f"Total Schemas with PII:     {schemas_with_pii}")
        lines.append(f"Total Tables Scanned:       {stats.get('tables_scanned', 'N/A')}")
        lines.append(f"Total Tables with PII:      {tables_with_pii}")
        lines.append(f"Total Columns scanned:      {stats.get('columns_scanned', 'N/A')}")
        lines.append(f"Unique Columns with PII:    {columns_with_pii}")
        lines.append("")
        
        if duration:
             lines.append(f"Scan Duration: {duration:.2f} seconds")
             lines.append("")

        # Detailed Report (Hierarchical)
        lines.append("Detailed Report")
        lines.append("-" * 80)
        
        if not findings:
            lines.append("No PII found.")
        else:
            # Organize findings: Schema -> Table -> Column -> [Findings]
            grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
            for f in findings:
                grouped[f['schema_name']][f['table_name']][f['column_name']].append(f)
                
            # Iterate and print
            for schema_name in sorted(grouped.keys()):
                lines.append(f"Schema: {schema_name}")
                
                for table_name in sorted(grouped[schema_name].keys()):
                    lines.append(f"    Table: {table_name}")
                    lines.append(f"        Columns:")
                    
                    for col_name in sorted(grouped[schema_name][table_name].keys()):
                        col_findings = grouped[schema_name][table_name][col_name]
                        # Format: col_name - Element1, Element2 (Source)
                        
                         # Group by element name to detail types
                        elements = []
                        for f in col_findings:
                            source_tag = f" ({f.get('source', 'Metadata')})" if f.get('source') == 'Content' else ""
                            elements.append(f"{f['element_name']}{source_tag}")
                        
                        elements_str = ", ".join(sorted(set(elements)))
                        lines.append(f"            - {col_name}: {elements_str}")
                    
                    lines.append("") # Spacer between tables
        
        # User Data Map Section
        lines.append("")
        lines.append("User Data Map")
        lines.append("-" * 80)
        
        if not user_data_map:
            lines.append("No user data mapping available (no user ID columns identified).")
        else:
            lines.append(f"{'User ID':<20} | Data Elements Collected")
            lines.append("-" * 80)
            
            for user_id in sorted(user_data_map.keys(), key=lambda x: (x.isdigit(), int(x) if x.isdigit() else x)):
                user_elements = user_data_map[user_id]
                # Flatten all elements across all locations
                all_elements = set()
                for location, elements in user_elements.items():
                    all_elements.update(elements)
                
                elements_str = ", ".join(sorted(all_elements))
                # Truncate user_id if too long
                user_id_display = user_id[:18] + ".." if len(user_id) > 20 else user_id
                lines.append(f"{user_id_display:<20} | {elements_str}")
        
        return "\n".join(lines)

    @staticmethod
    @staticmethod
    def generate_json_report(findings: List[Dict[str, Any]], duration: Optional[float] = None,
                            db_connection_info: Optional[str] = None, report_id: Optional[str] = None,
                            stats: Dict[str, int] = None,
                            user_data_map: Dict[str, Dict[str, Set[str]]] = None) -> Dict[str, Any]:
        """Generate JSON report."""
        if stats is None:
            stats = {}
        if user_data_map is None:
            user_data_map = {}
            
        # Convert user_data_map sets to lists for JSON serialization
        json_user_map = {}
        for user_id, data_map in user_data_map.items():
            json_user_map[user_id] = {k: list(v) for k, v in data_map.items()}

        return {
            "application": "truscanner",
            "report_type": "database_schema",
            "scan_report_id": report_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "database_info": db_connection_info,
            "scan_duration_seconds": duration,
            "scan_stats": stats,
            "total_findings": len(findings),
            "user_data_map_summary": {
                "unique_users_mapped": len(user_data_map)
            },
            "user_data_map": json_user_map,
            "findings_summary": {
                "metadata_findings": len([f for f in findings if f.get('source') != 'Content']),
                "content_findings": len([f for f in findings if f.get('source') == 'Content'])
            },
            "findings": findings
        }
