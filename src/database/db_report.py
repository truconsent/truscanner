from typing import List, Dict, Any, Optional
from collections import defaultdict
import datetime

class DatabaseReportGenerator:
    """Generates formatted reports for database scan findings."""
    
    @staticmethod
    def generate_report(findings: List[Dict[str, Any]], duration: Optional[float] = None, 
                       db_connection_info: Optional[str] = None, report_id: Optional[str] = None) -> str:
        """Generate formatted TXT report."""
        if not findings:
            return "truconsent (truconsent.io)\n\ntruscanner Database Report\n\nNo PII data elements found in database schema."
            
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
        
        # Summary
        lines.append("Summary")
        lines.append("-" * 80)
        lines.append(f"Total Findings: {len(findings)}")
        if duration:
            lines.append(f"Time Taken: {duration:.2f} seconds")
        
        # Count unique tables and schemas
        schemas = set(f['schema_name'] for f in findings)
        tables = set((f['schema_name'], f['table_name']) for f in findings)
        lines.append(f"Schemas with PII: {len(schemas)}")
        lines.append(f"Tables with PII: {len(tables)}")
        lines.append("")
        
        # Summary by Category
        category_counts = defaultdict(int)
        for f in findings:
            category_counts[f['element_category']] += 1
            
        lines.append("Findings by Category")
        lines.append("-" * 80)
        for cat, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"{cat}: {count}")
        lines.append("")
        
        # Findings Detail
        lines.append("Detailed Findings")
        lines.append("-" * 80)
        lines.append(f"{'Schema':<20} {'Table':<30} {'Column':<30} {'Data Element'}")
        lines.append("-" * 80)
        
        # Sort by schema, table, column
        sorted_findings = sorted(findings, key=lambda x: (x['schema_name'], x['table_name'], x['column_name']))
        
        for f in sorted_findings:
            schema = f['schema_name'][:18] + ".." if len(f['schema_name']) > 20 else f['schema_name']
            table = f['table_name'][:28] + ".." if len(f['table_name']) > 30 else f['table_name']
            column = f['column_name'][:28] + ".." if len(f['column_name']) > 30 else f['column_name']
            element = f['element_name']
            
            lines.append(f"{schema:<20} {table:<30} {column:<30} {element}")
            
        return "\n".join(lines)

    @staticmethod
    def generate_json_report(findings: List[Dict[str, Any]], duration: Optional[float] = None,
                            db_connection_info: Optional[str] = None, report_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate JSON report."""
        return {
            "application": "truscanner",
            "report_type": "database_schema",
            "scan_report_id": report_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "database_info": db_connection_info,
            "scan_duration_seconds": duration,
            "total_findings": len(findings),
            "findings": findings
        }
