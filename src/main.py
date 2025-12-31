import click
import json
from .scanner import scan_directory

@click.group()
def main():
    pass

@main.command()
@click.argument('directory', type=click.Path(exists=True))
def scan(directory):
    """Scan a directory using Regex, Presidio, and AI."""
    click.echo(f"Scanning directory: {directory}...")
    
    results = scan_directory(directory)
    
    if results:
        click.echo(json.dumps(results, indent=2))
    else:
        click.echo("No data elements found.")

if __name__ == "__main__":
    main()