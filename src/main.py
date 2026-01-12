import click
import json
import time
import os
import warnings

# Suppress urllib3 NotOpenSSLWarning which is common on macOS with LibreSSL
warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")
from .scanner import scan_directory
from .regex_scanner import RegexScanner
from .api_client import truscannerAPI

@click.group()
def main():
    pass

@main.command()
@click.argument('directory', type=click.Path(exists=True))
@click.option('--with-presidio', is_flag=True, help='Enable Presidio NLP scanner (requires model download)')
@click.option('--with-ai', is_flag=True, help='Enable AI/LLM scanner (requires OPENAI_API_KEY)')
@click.option('--format', type=click.Choice(['json', 'report']), default='report', help='Output format')
@click.option('--output', '-o', type=click.Path(), help='Save report to file')
@click.option('--stored-only', is_flag=True, help='Only report data elements that flow into a storage sink')
def scan(directory, with_presidio, with_ai, format, output, stored_only):
    """Scan a directory for privacy-related data elements.
    
    By default, uses fast regex-based scanning with patterns from JSON files.
    Use --with-presidio or --with-ai to enable additional scanners.
    """
    click.echo(f"Scanning: {directory}...")
    
    results = []
    duration = 0
    files_scanned = 0
    
    # Default: Use regex scanner (fast, no downloads)
    if not with_presidio and not with_ai:
        scanner = RegexScanner()
        
        start_time = time.time()
        results, files_scanned = scanner.scan_directory(directory)
        duration = time.time() - start_time
        
        if format == 'report':
            report = scanner.generate_report(results, duration=duration, stored_only=stored_only)
            click.echo(report)
            
            # Auto-save report to file
            output_file = output or "scan_report.txt"
            with open(output_file, 'w') as f:
                f.write(report)
            click.echo(f"\n✅ Report saved to: {output_file}")
        else:
            click.echo(json.dumps(results, indent=2))
            if output:
                with open(output, 'w') as f:
                    json.dump(results, f, indent=2)
                click.echo(f"\n✅ Results saved to: {output}")
    else:
        # Use full scanner with optional Presidio and AI
        start_time = time.time()
        results = scan_directory(directory, use_presidio=with_presidio, use_ai=with_ai)
        duration = time.time() - start_time
        
        if results:
            if format == 'report':
                # Generate a formatted report
                click.echo(f"\n{'='*80}")
                click.echo(f"SCAN RESULTS")
                click.echo(f"{'='*80}")
                click.echo(f"\nTotal Findings: {len(results)}\n")
                
                # Group by file
                by_file = {}
                for r in results:
                    fname = r.get('filename', 'Unknown')
                    if fname not in by_file:
                        by_file[fname] = []
                    by_file[fname].append(r)
                
                for fname, findings in by_file.items():
                    click.echo(f"\n📄 {fname}")
                    click.echo(f"   Found {len(findings)} data element(s)")
                    for f in findings[:5]:  # Show first 5
                        click.echo(f"   - Line {f.get('line_number', '?')}: {f.get('element_name', 'Unknown')} (Source: {f.get('source', 'Unknown')})")
                    if len(findings) > 5:
                        click.echo(f"   ... and {len(findings) - 5} more")
                
                if output:
                    with open(output, 'w') as f:
                        json.dump(results, f, indent=2)
                    click.echo(f"\n✅ Full results saved to: {output}")
            else:
                click.echo(json.dumps(results, indent=2))
                if output:
                    with open(output, 'w') as f:
                        json.dump(results, f, indent=2)
                    click.echo(f"\n✅ Results saved to: {output}")
        else:
            click.echo("No data elements found.")

    # Universal post-scan analytics prompt
    if results and click.confirm("\n✅ Scan complete! Would you like to view analytics on the dashboard?", default=True):
        api = truscannerAPI()
        
        # Always authenticate if not already authenticated
        if not api.is_authenticated():
            click.echo("🔐 Authentication required to upload scan data...")
            click.echo("🔐 Starting authentication flow...")
            click.echo("📱 Opening browser for Google sign-in...")
            click.echo("⏳ Waiting for authentication (timeout: 5 minutes)...")
            
            if not api.authenticate():
                click.echo("❌ Authentication failed or cancelled. Scan saved locally only.")
                return
            click.echo("✅ Authenticated successfully!")
        
        click.echo("📤 Uploading results to truscanner Analytics...")
        
        # Use directory name as project name if possible
        project_name = os.path.basename(os.path.abspath(directory))
        
        # Filter to stored-only for upload (show only PII that flows to storage)
        stored_results = [r for r in results if r.get("is_stored")]
        
        response = api.upload_scan(
            project_name=project_name,
            results=stored_results,
            duration=duration,
            files_scanned=files_scanned,
            metadata={"cli_version": "0.2.0"}
        )
        
        # If unauthorized, re-authenticate and retry
        if response and response.get("error") == "unauthorized":
            click.echo("🔐 Re-authenticating...")
            if api.authenticate():
                click.echo("✅ Authenticated successfully!")
                click.echo("📤 Retrying upload...")
                response = api.upload_scan(
                    project_name=project_name,
                    results=stored_results,
                    duration=duration,
                    files_scanned=files_scanned,
                    metadata={"cli_version": "0.2.0"}
                )
            else:
                click.echo("❌ Authentication failed. Scan saved locally only.")
                return
        
        if response and "id" in response:
            api.open_dashboard(response["id"])
        else:
            click.echo("❌ Failed to upload results. Please try again later.")

if __name__ == "__main__":
    main()