import click
import json
import os
import time

from . import __version__
from .ai_scanner import AIScanner
from .regex_scanner import RegexScanner
from .report_utils import (
    create_reports_subdirectory,
    generate_report_id,
    get_next_report_filename,
    get_reports_directory,
)
from .scanner import run_ai_scan, run_regex_scan
from .utils import (
    get_ai_provider_setup_help,
    get_bedrock_model_id,
    get_missing_provider_requirements,
    normalize_ai_provider,
    select_ai_provider,
    select_file_format,
    load_runtime_env,
    select_ollama_model,
    show_progress,
    upload_to_backend,
)

load_runtime_env()


PERSONAL_CATEGORIES = [
    'Personal Identifiable Information',
    'PII',
    'Contact Information',
    'Government-Issued Identifiers',
    'Authentication & Credentials',
    'Health & Biometric Data',
    'Sensitive Personal Data',
]


def _filter_personal_findings(findings):
    return [
        finding
        for finding in findings
        if any(cat in finding.get('element_category', '') for cat in PERSONAL_CATEGORIES)
    ]


def _file_types_to_generate(file_type: str):
    return ['txt', 'md', 'json'] if file_type == 'all' else [file_type]


def _save_reports(scanner, findings, duration, report_id, directory, reports_subdir, file_types, base_name):
    saved_files = []

    for file_type in file_types:
        filename = get_next_report_filename(reports_subdir, file_type, base_name=base_name)
        filepath = reports_subdir / filename

        if file_type == 'txt':
            report = scanner.generate_report(
                findings,
                duration=duration,
                report_id=report_id,
                directory_scanned=directory,
            )
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(report)
        elif file_type == 'md':
            report = scanner.generate_markdown_report(
                findings,
                duration=duration,
                report_id=report_id,
                directory_scanned=directory,
            )
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(report)
        elif file_type == 'json':
            report = scanner.generate_json_report(
                findings,
                duration=duration,
                report_id=report_id,
                directory_scanned=directory,
            )
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

        saved_files.append(str(filepath))

    return saved_files


def _echo_saved_files(title, filepaths):
    click.echo(f"\n{title}")
    for filepath in filepaths:
        click.echo(f"  ✅ {filepath}")


def _show_scan_summary(report_id, findings, duration, saved_files):
    click.echo(f"\n{'='*80}")
    click.echo(f"Scan Report ID: {report_id}")
    click.echo(f"{'='*80}")
    click.echo(f"\nTotal Findings: {len(findings)}")
    click.echo(f"Time Taken: {duration:.2f} seconds")
    _echo_saved_files("Reports saved to:", saved_files)


def _prepare_ai_scan(provider: str, ai_mode: str):
    normalized_provider = normalize_ai_provider(provider)
    missing = get_missing_provider_requirements(normalized_provider)

    if missing:
        click.echo(f"\n❌ {normalized_provider.title()} credentials are not configured.")
        click.echo(f"Missing: {', '.join(missing)}")
        for line in get_ai_provider_setup_help(normalized_provider):
            click.echo(line)
        return False, None

    if normalized_provider == 'ollama':
        ai_scanner = AIScanner(ai_mode=ai_mode)
        available_models = ai_scanner.get_available_ollama_models()
        if not available_models:
            click.echo("\n❌ No Ollama models found. Please ensure Ollama is running and models are downloaded.")
            for line in get_ai_provider_setup_help('ollama'):
                click.echo(line)
            return False, None
        selected_model = select_ollama_model(available_models)
        click.echo(f"\nRunning enhanced AI scan with Ollama model: {selected_model} ({ai_mode} mode)...")
        return True, selected_model

    if normalized_provider == 'openai':
        click.echo(f"\nRunning enhanced AI scan with OpenAI ({ai_mode} mode)...")
        return True, None

    if normalized_provider == 'bedrock':
        bedrock_model = get_bedrock_model_id(default=AIScanner.DEFAULT_BEDROCK_MODEL)
        click.echo(
            f"\nRunning enhanced AI scan with AWS Bedrock model: {bedrock_model} ({ai_mode} mode)..."
        )
        return True, bedrock_model

    return False, None


@click.group(context_settings=dict(help_option_names=['-h', '--help']))
@click.version_option(version=__version__, prog_name="truscanner")
def main():
    pass


@main.command()
@click.argument('directory', type=click.Path(exists=True))
@click.option('--with-ai', is_flag=True, help='Enable the separate AI scan after the regex scan')
@click.option(
    '--ai-provider',
    type=click.Choice(['ollama', 'openai', 'bedrock'], case_sensitive=False),
    help='AI provider to use for the AI-only scan',
)
@click.option(
    '--ai-mode',
    type=click.Choice(['fast', 'balanced', 'full'], case_sensitive=False),
    default='balanced',
    show_default=True,
    help='AI scan mode: fast (speed), balanced (default), full (max coverage)',
)
@click.option('--format', type=click.Choice(['json', 'report']), default='report', help='Output format (deprecated, use interactive prompt)')
@click.option('--output', '-o', type=click.Path(), help='Save report to file (deprecated, reports saved to reports/)')
@click.option('--personal-only', is_flag=True, help='Only report personal identifiable information (PII) data elements')
def scan(directory, with_ai, ai_provider, ai_mode, format, output, personal_only):
    """Scan a directory for privacy-related data elements."""
    file_type = select_file_format()
    ai_mode = (ai_mode or "balanced").lower()

    click.echo(f"\nScanning: {directory}...")

    report_id = generate_report_id(directory)
    scanner = None
    configured_elements = 0
    try:
        scanner = RegexScanner()
        configured_elements = len(getattr(scanner, "data_elements", []) or [])
    except Exception:
        scanner = None
        configured_elements = 0

    if scanner is None:
        scanner = RegexScanner()

    if configured_elements:
        click.echo(f"Loaded data element definitions: {configured_elements}")

    def progress_callback(current, total, file_path):
        show_progress(current, total, file_path)

    regex_start_time = time.time()
    regex_results = run_regex_scan(
        directory,
        progress_callback=progress_callback,
        regex_scanner=scanner,
    )
    regex_duration = time.time() - regex_start_time

    if personal_only:
        regex_results = _filter_personal_findings(regex_results)

    reports_dir = get_reports_directory()
    reports_subdir = create_reports_subdirectory(reports_dir, directory)
    file_types = _file_types_to_generate(file_type)

    saved_files = _save_reports(
        scanner,
        regex_results,
        regex_duration,
        report_id,
        directory,
        reports_subdir,
        file_types,
        base_name="truscan_report",
    )
    _show_scan_summary(report_id, regex_results, regex_duration, saved_files)

    selected_provider = normalize_ai_provider(ai_provider)
    if selected_provider is None:
        default_provider = None if with_ai else "skip"
        selected_provider = select_ai_provider(default_provider=default_provider)

    if selected_provider:
        should_run_ai, selected_model = _prepare_ai_scan(selected_provider, ai_mode)
        if should_run_ai:
            ai_start_time = time.time()
            ai_results = run_ai_scan(
                directory,
                ai_provider=selected_provider,
                ai_mode=ai_mode,
                model=selected_model,
            )
            ai_duration = time.time() - ai_start_time

            if personal_only:
                ai_results = _filter_personal_findings(ai_results)

            if ai_results:
                ai_saved_files = _save_reports(
                    scanner,
                    ai_results,
                    ai_duration,
                    report_id,
                    directory,
                    reports_subdir,
                    file_types,
                    base_name="truscan_report_llm",
                )
                click.echo(f"\nEnhanced findings: {len(ai_results)}")
                _echo_saved_files("Enhanced reports saved to:", ai_saved_files)
            else:
                click.echo("\nNo additional data elements found by AI.")

    analyze = click.prompt(
        "\nDo you want to upload the scan report for the above purpose?",
        type=click.Choice(['Y', 'N'], case_sensitive=False),
        default='Y',
        show_default=False,
    )

    if analyze.upper() == 'Y' or analyze == '':
        project_name = os.path.basename(os.path.normpath(directory)) or "Untitled Project"
        unique_files = len(set(r.get('filename') for r in regex_results if r.get('filename')))

        metadata = {
            "cli_version": __version__,
            "directory_scanned": directory,
        }

        success = upload_to_backend(
            scan_report_id=report_id,
            project_name=project_name,
            duration=regex_duration,
            total_findings=len(regex_results),
            scan_data=regex_results,
            files_scanned=unique_files,
            metadata=metadata,
        )

        if success:
            click.echo("✅ Scan results uploaded to backend successfully!")
            click.echo(f"Scan Report ID: {report_id}")
            click.echo(f"View scan report online: https://app.truconsent.io/scan/{report_id}")


if __name__ == "__main__":
    main()
