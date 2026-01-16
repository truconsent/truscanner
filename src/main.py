import click
import json
import time
import os
from pathlib import Path
from .scanner import scan_directory
from .regex_scanner import RegexScanner
from .report_utils import (
    generate_report_id,
    get_reports_directory,
    create_reports_subdirectory,
    get_next_report_filename
)
from .utils import select_file_format, show_progress, upload_to_backend

@click.group(context_settings=dict(help_option_names=['-h', '--help']))
@click.version_option(version="0.2.3", prog_name="truscanner")
def main():
    pass

@main.command()
@click.argument('directory', type=click.Path(exists=True))
@click.option('--with-presidio', is_flag=True, help='Enable Presidio NLP scanner (requires model download)')
@click.option('--with-ai', is_flag=True, help='Enable AI/LLM scanner (requires OPENAI_API_KEY)')
@click.option('--format', type=click.Choice(['json', 'report']), default='report', help='Output format (deprecated, use interactive prompt)')
@click.option('--output', '-o', type=click.Path(), help='Save report to file (deprecated, reports saved to Reports/)')
@click.option('--personal-only', is_flag=True, help='Only report personal identifiable information (PII) data elements')
def scan(directory, with_presidio, with_ai, format, output, personal_only):
    """Scan a directory for privacy-related data elements.
    
    By default, uses fast regex-based scanning with patterns from JSON files.
    Use --with-presidio or --with-ai to enable additional scanners.
    """
    # Interactive file type selection with arrow menu
    file_type = select_file_format()
    
    click.echo(f"\nScanning: {directory}...")
    
    # Generate report ID
    report_id = generate_report_id(directory)
    
    # Default: Use regex scanner (fast, no downloads)
    if not with_presidio and not with_ai:
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
                "cli_version": "0.2.0",
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
        # Use full scanner with optional Presidio and AI
        # Note: Presidio/AI scanner doesn't support progress callback yet
        start_time = time.time()
        results = scan_directory(directory, use_presidio=with_presidio, use_ai=with_ai)
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
                    "cli_version": "0.2.0",
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