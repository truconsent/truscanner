import click
import json
import time
from .scanner import scan_directory
from .regex_scanner import RegexScanner

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
    
    # Default: Use regex scanner (fast, no downloads)
    if not with_presidio and not with_ai:
        scanner = RegexScanner()
        
        start_time = time.time()
        results = scanner.scan_directory(directory)
        duration = time.time() - start_time
        
        if format == 'report':
            report = scanner.generate_report(results, duration=duration, stored_only=stored_only)
            click.echo(report)
            
            # Auto-save report to file
            output_file = output or "scan_report.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
            click.echo(f"\n✅ Report saved to: {output_file}")
        else:
            click.echo(json.dumps(results, indent=2))
            if output:
                with open(output, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2)
                click.echo(f"\n✅ Results saved to: {output}")
    else:
        # Use full scanner with optional Presidio and AI
        results = scan_directory(directory, use_presidio=with_presidio, use_ai=with_ai)
        
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
                    with open(output, 'w', encoding='utf-8') as f:
                        json.dump(results, f, indent=2)
                    click.echo(f"\n✅ Full results saved to: {output}")
            else:
                click.echo(json.dumps(results, indent=2))
                if output:
                    with open(output, 'w', encoding='utf-8') as f:
                        json.dump(results, f, indent=2)
                    click.echo(f"\n✅ Results saved to: {output}")
        else:
            click.echo("No data elements found.")

if __name__ == "__main__":
    main()