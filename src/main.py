import click
import json
import time
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from .scanner import scan_directory
from .regex_scanner import RegexScanner
from .ai_scanner import AIScanner
from .report_utils import (
    generate_report_id,
    get_reports_directory,
    create_reports_subdirectory,
    get_next_report_filename
)
from .utils import select_file_format, select_ollama_model, show_progress, upload_to_backend
from . import __version__
from .database import DatabaseConnectorFactory
from .database.ui import select_database_type, collect_credentials

@click.group(context_settings=dict(help_option_names=['-h', '--help']))
@click.version_option(version=__version__, prog_name="truscanner")
def main():
    pass

@main.command()
@click.option('--test-only', is_flag=True, help='Only test the connection, do not scan')
def db_scan(test_only):
    """Scan a database for privacy-related data elements.
    
    Interactively select your database type and provide connection details.
    """
    try:
        # Step 1: Check for environment variable bypass
        env_conn_str = os.getenv('POSTGRES_CONNECTION_STRING')
        if env_conn_str:
            click.echo("Using connection string from POSTGRES_CONNECTION_STRING environment variable.")
            try:
                from sqlalchemy.engine.url import make_url
                url = make_url(env_conn_str)
                db_type = 'PostgreSQL' # Assumes postgres based on var name/scheme
                credentials = {
                    'host': url.host,
                    'port': url.port or 5432,
                    'database': url.database,
                    'username': url.username,
                    'password': url.password
                }
            except Exception as e:
                click.echo(f"❌ Error parsing connection string: {e}")
                return
        else:
            # Step 1: Select database type
            try:
                db_type = select_database_type()
                
                # Step 2: Collect credentials
                credentials = collect_credentials(db_type)
            except Exception as e:
                click.echo(f"Error during selection: {e}")
                return
        
        # Step 3: Create connection
        factory = DatabaseConnectorFactory()
        adapter = factory.create_adapter(db_type, credentials)
            
        click.echo(f"\nConnecting to {db_type}...")
        
        # Step 4: Test connection
        success, message = adapter.test_connection()
        if success:
            click.echo(f"✅ {message}")
        else:
            click.echo(f"❌ {message}")
            return
        
        if test_only:
            return
            
        # Phase 2: Schema Scanning
        from .database.db_scanner import DatabaseSchemaScanner
        from .database.db_report import DatabaseReportGenerator
        from .report_utils import get_reports_directory, create_reports_subdirectory, get_next_report_filename, generate_report_id
        from .utils import upload_to_backend
        
        click.echo("\n🔍 Scanning database schema for PII...")
        start_time = time.time()
        
        scanner = DatabaseSchemaScanner()
        findings, stats, user_data_map = scanner.scan_database(adapter)
        duration = time.time() - start_time
        
        # Display summary
        click.echo(f"\nScanning complete in {duration:.2f}s")
        click.echo(f"Total Findings: {len(findings)}")
        click.echo(f"Unique Users Mapped: {len(user_data_map)}")
        
        # Generate Reports (even if no findings, we may have user map)
        reports_dir = get_reports_directory()
        # Use database type and host as directory name
        db_identifier = f"{db_type}_{credentials.get('database', 'unknown')}"
        reports_subdir = create_reports_subdirectory(reports_dir, db_identifier)
        
        # Generate Report ID
        report_id = generate_report_id(db_identifier)
        
        # Generate TXT Report
        report_txt = DatabaseReportGenerator.generate_report(
            findings, 
            duration, 
            f"{db_type} - {credentials.get('host', 'local')}", 
            report_id,
            stats=stats,
            user_data_map=user_data_map
        )
        filename_txt = get_next_report_filename(reports_subdir, 'txt', base_name='db_scan_report')
        with open(reports_subdir / filename_txt, 'w', encoding='utf-8') as f:
            f.write(report_txt)
        click.echo(f"  ✅ Report saved: {reports_subdir / filename_txt}")
        
        # Generate JSON Report
        report_json = DatabaseReportGenerator.generate_json_report(
            findings, 
            duration, 
            f"{db_type} - {credentials.get('host', 'local')}", 
            report_id,
            stats=stats,
            user_data_map=user_data_map
        )
        filename_json = get_next_report_filename(reports_subdir, 'json', base_name='db_scan_report')
        with open(reports_subdir / filename_json, 'w', encoding='utf-8') as f:
            json.dump(report_json, f, indent=2, ensure_ascii=False, default=list)
        click.echo(f"  ✅ JSON saved:   {reports_subdir / filename_json}")
        
        # Display Report ID
        click.echo(f"\n{'='*80}")
        click.echo(f"Scan Report ID: {report_id}")
        click.echo(f"View scan report online: https://app.truconsent.io/scan/{report_id}")
        click.echo(f"{'='*80}")
        
        # Post-scan analysis prompt
        analyze = click.prompt(
            "\nDo you want to upload the scan report for the above purpose?",
            type=click.Choice(['Y', 'N'], case_sensitive=False),
            default='Y',
            show_default=False
        )
        
        if analyze.upper() == 'Y':
            project_name = db_identifier
            
            # Count unique tables/schemas as "files"
            unique_files = len(set((f['schema_name'], f['table_name']) for f in findings)) if findings else 0
            
            metadata = {
                "cli_version": __version__,
                "database_type": db_type,
                "host": credentials.get('host', 'unknown')
            }
            
            success = upload_to_backend(
                scan_report_id=report_id,
                project_name=project_name,
                duration=duration,
                total_findings=len(findings),
                scan_data=findings,
                files_scanned=unique_files,
                metadata=metadata
            )
            
            if success:
                click.echo("✅ Scan results uploaded to backend successfully!")
                click.echo(f"Scan Report ID: {report_id}")
                click.echo(f"View scan report online: https://app.truconsent.io/scan/{report_id}")
        
        # Cleanup
        adapter.disconnect()
        
    except KeyboardInterrupt:
        click.echo("\n\nOperation cancelled by user.")
    except Exception as e:
        click.echo(f"\n❌ Error: {str(e)}")

@main.command()
@click.argument('directory', type=click.Path(exists=True))
@click.option('--with-ai', is_flag=True, help='Enable AI/LLM scanner (requires OPENAI_API_KEY)')
@click.option('--format', type=click.Choice(['json', 'report']), default='report', help='Output format (deprecated, use interactive prompt)')
@click.option('--output', '-o', type=click.Path(), help='Save report to file (deprecated, reports saved to reports/)')
@click.option('--personal-only', is_flag=True, help='Only report personal identifiable information (PII) data elements')
def scan(directory, with_ai, format, output, personal_only):
    """Scan a directory for privacy-related data elements.
    
    By default, uses fast regex-based scanning with patterns from JSON files.
    Use --with-ai to enable additional scanners.
    """
    # Interactive file type selection with arrow menu
    file_type = select_file_format()
    
    click.echo(f"\nScanning: {directory}...")
    
    # Generate report ID
    report_id = generate_report_id(directory)
    
    # Default: Use regex scanner (fast, no downloads)
    if not with_ai:
        scanner = RegexScanner()
        
        # Progress callback
        def progress_callback(current, total, file_path):
            show_progress(current, total, file_path)
        
        start_time = time.time()
        results = scanner.scan_directory(directory, progress_callback=progress_callback)
        duration = time.time() - start_time
        
        # Filter to personal details only if requested
        if personal_only:
            personal_categories = [
                'Personal Identifiable Information',
                'PII',
                'Contact Information',
                'Government-Issued Identifiers',
                'Authentication & Credentials',
                'Health & Biometric Data',
                'Sensitive Personal Data'
            ]
            results = [r for r in results if any(cat in r.get('element_category', '') for cat in personal_categories)]
        
        # Create Reports directory structure
        reports_dir = get_reports_directory()
        reports_subdir = create_reports_subdirectory(reports_dir, directory)
        
        # Determine which file types to generate
        file_types_to_generate = []
        if file_type == 'all':
            file_types_to_generate = ['txt', 'md', 'json']
        else:
            file_types_to_generate = [file_type]
        
        saved_files = []
        
        # Generate and save reports
        for ft in file_types_to_generate:
            filename = get_next_report_filename(reports_subdir, ft)
            filepath = reports_subdir / filename
            
            if ft == 'txt':
                report = scanner.generate_report(results, duration=duration, report_id=report_id, directory_scanned=directory)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(report)
                saved_files.append(str(filepath))
            elif ft == 'md':
                markdown_report = scanner.generate_markdown_report(
                    results, 
                    duration=duration, 
                    report_id=report_id,
                    directory_scanned=directory
                )
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(markdown_report)
                saved_files.append(str(filepath))
            elif ft == 'json':
                json_report = scanner.generate_json_report(
                    results,
                    duration=duration,
                    report_id=report_id,
                    directory_scanned=directory
                )
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(json_report, f, indent=2, ensure_ascii=False)
                saved_files.append(str(filepath))
        
        # Display results
        click.echo(f"\n{'='*80}")
        click.echo(f"Scan Report ID: {report_id}")
        click.echo(f"{'='*80}")
        click.echo(f"\nTotal Findings: {len(results)}")
        if duration is not None:
            click.echo(f"Time Taken: {duration:.2f} seconds")
        click.echo(f"\nReports saved to:")
        for filepath in saved_files:
            click.echo(f"  ✅ {filepath}")
        
        # Enhanced LLM Scan Prompt
        enhanced_scan = click.prompt(
            "\nDo you want to use Ollama/AI for enhanced PII detection (find what regex missed)?",
            type=click.Choice(['Y', 'N'], case_sensitive=False),
            default='N',
            show_default=False
        )
        
        if enhanced_scan.upper() == 'Y':
            use_openai = bool(os.environ.get("OPENAI_API_KEY"))
            ai_scanner = AIScanner()
            selected_model = None
            
            if use_openai:
                click.echo("\nRunning enhanced AI scan with OpenAI...")
            else:
                available_models = ai_scanner.get_available_ollama_models()
                if not available_models:
                    click.echo("\n❌ No Ollama models found. Please ensure Ollama is running and models are downloaded.")
                    click.echo("   Download models using: ollama pull llama3")
                else:
                    selected_model = select_ollama_model(available_models)
                    click.echo(f"\nRunning enhanced AI scan with Ollama model: {selected_model}...")
            
            if use_openai or selected_model:
                ai_start_time = time.time()
                ai_results = ai_scanner.scan_directory(directory, use_openai=use_openai, model=selected_model)
                ai_duration = time.time() - ai_start_time
            
            if ai_results:
                llm_saved_files = []
                for ft in file_types_to_generate:
                    # Generate filename with 'llm' suffix
                    llm_base_name = "truscan_report_llm"
                    filename = get_next_report_filename(reports_subdir, ft, base_name=llm_base_name)
                    filepath = reports_subdir / filename
                    
                    if ft == 'txt':
                        report = scanner.generate_report(ai_results, duration=ai_duration, report_id=report_id, directory_scanned=directory)
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(report)
                        llm_saved_files.append(str(filepath))
                    elif ft == 'md':
                        markdown_report = scanner.generate_markdown_report(
                            ai_results, 
                            duration=ai_duration, 
                            report_id=report_id,
                            directory_scanned=directory
                        )
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(markdown_report)
                        llm_saved_files.append(str(filepath))
                    elif ft == 'json':
                        json_report = scanner.generate_json_report(
                            ai_results,
                            duration=ai_duration,
                            report_id=report_id,
                            directory_scanned=directory
                        )
                        with open(filepath, 'w', encoding='utf-8') as f:
                            json.dump(json_report, f, indent=2, ensure_ascii=False)
                        llm_saved_files.append(str(filepath))
                
                click.echo(f"\nEnhanced findings: {len(ai_results)}")
                click.echo(f"Enhanced reports saved to:")
                for filepath in llm_saved_files:
                    click.echo(f"  ✅ {filepath}")
            else:
                click.echo("\nNo additional data elements found by AI.")

        # Post-scan analysis prompt
        analyze = click.prompt(
            "\nDo you want to upload the scan report for the above purpose?",
            type=click.Choice(['Y', 'N'], case_sensitive=False),
            default='Y',
            show_default=False
        )
        
        if analyze.upper() == 'Y' or analyze == '':
            # Extract project name from directory
            project_name = os.path.basename(os.path.normpath(directory)) or "Untitled Project"
            
            # Count unique files scanned
            unique_files = len(set(r.get('filename') for r in results if r.get('filename')))
            
            metadata = {
                "cli_version": __version__,
                "directory_scanned": directory
            }
            
            success = upload_to_backend(
                scan_report_id=report_id,
                project_name=project_name,
                duration=duration,
                total_findings=len(results),
                scan_data=results,
                files_scanned=unique_files,
                metadata=metadata
            )
            
            if success:
                click.echo("✅ Scan results uploaded to backend successfully!")
                click.echo(f"Scan Report ID: {report_id}")
                click.echo(f"View scan report online: https://app.truconsent.io/scan/{report_id}")
    else:
        # Use full scanner with optional AI
        # Note: AI scanner doesn't support progress callback yet
        start_time = time.time()
        results = scan_directory(directory, use_ai=with_ai)
        duration = time.time() - start_time
        
        if results:
            # Filter to personal details only if requested
            if personal_only:
                personal_categories = [
                    'Personal Identifiable Information',
                    'PII',
                    'Contact Information',
                    'Government-Issued Identifiers',
                    'Authentication & Credentials',
                    'Health & Biometric Data',
                    'Sensitive Personal Data'
                ]
                results = [r for r in results if any(cat in r.get('element_category', '') for cat in personal_categories)]
            
            # Create Reports directory structure
            reports_dir = get_reports_directory()
            reports_subdir = create_reports_subdirectory(reports_dir, directory)
            
            # Determine which file types to generate
            file_types_to_generate = []
            if file_type == 'all':
                file_types_to_generate = ['txt', 'md', 'json']
            else:
                file_types_to_generate = [file_type]
            
            saved_files = []
            scanner = RegexScanner()
            
            # Generate and save reports
            for ft in file_types_to_generate:
                filename = get_next_report_filename(reports_subdir, ft)
                filepath = reports_subdir / filename
                
                if ft == 'txt':
                    report = scanner.generate_report(results, duration=duration, report_id=report_id)
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(report)
                    saved_files.append(str(filepath))
                elif ft == 'md':
                    markdown_report = scanner.generate_markdown_report(
                        results, 
                        duration=duration, 
                        report_id=report_id,
                        directory_scanned=directory
                    )
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(markdown_report)
                    saved_files.append(str(filepath))
                elif ft == 'json':
                    json_report = scanner.generate_json_report(
                        results,
                        duration=duration,
                        report_id=report_id,
                        directory_scanned=directory
                    )
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(json_report, f, indent=2, ensure_ascii=False)
                    saved_files.append(str(filepath))
            
            # Display results
            click.echo(f"\n{'='*80}")
            click.echo(f"Scan Report ID: {report_id}")
            click.echo(f"View scan report online: https://app.truconsent.io/scan/{report_id}")
            click.echo(f"{'='*80}")
            click.echo(f"\nTotal Findings: {len(results)}")
            if duration is not None:
                click.echo(f"Time Taken: {duration:.2f} seconds")
            click.echo(f"\nReports saved to:")
            for filepath in saved_files:
                click.echo(f"  ✅ {filepath}")
            
            # Post-scan analysis prompt
            analyze = click.prompt(
                "\nDo you want to analyze?",
                type=click.Choice(['Y', 'y', 'N', 'n', ''], case_sensitive=False),
                default='Y',
                show_default=False
            )
            
            if analyze.upper() == 'Y' or analyze == '':
                # Extract project name from directory
                project_name = os.path.basename(os.path.normpath(directory)) or "Untitled Project"
                
                # Count unique files scanned
                unique_files = len(set(r.get('filename') for r in results if r.get('filename')))
                
                metadata = {
                    "cli_version": __version__,
                    "directory_scanned": directory
                }
                
                success = upload_to_backend(
                    scan_report_id=report_id,
                    project_name=project_name,
                    duration=duration,
                    total_findings=len(results),
                    scan_data=results,
                    files_scanned=unique_files,
                    metadata=metadata
                )
                
                if success:
                    click.echo("✅ Scan results uploaded successfully!")
        else:
            click.echo("No data elements found.")

if __name__ == "__main__":
    main()