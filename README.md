# truScanner from truConsent
![PyPI version](https://img.shields.io/pypi/v/truscanner.svg?cacheSeconds=300&v=0.2.10)
![License](https://img.shields.io/pypi/l/truscanner.svg)

**Open-Source Static Analysis for Privacy Data Flows**

`truScanner` is a static code analysis tool designed to discover and analyze personal data elements in your source code. It helps developers and security teams identify privacy-related data flows and generate comprehensive reports.

[📦 PyPI Project](https://pypi.org/project/truscanner/) • [🌐 App Dashboard](https://app.truconsent.io/)

## 🚀 Features

- **Comprehensive Detection**: Identifies 300+ personal data elements (PII, financial data, device identifiers, etc.)
- **Full Catalog Coverage**: Loads and scans against all configured data elements from `data_elements/` (not a truncated subset)
- **Interactive Menu**: Arrow-key navigable menu for selecting output formats
- **Real-time Progress**: Visual progress indicator during scanning
- **Multiple Report Formats**: Generate reports in TXT, Markdown, or JSON format
- **Separate Regex and AI Scans**: Regex/static scanning and AI-enhanced scanning now run as distinct paths
- **AI-Powered Enhancement**: Optional integration with Ollama, OpenAI, or AWS Bedrock for deeper context
- **Backend Integration**: Optional upload to backend API for centralized storage
- **Auto-incrementing Reports**: Automatically manages report file naming to prevent overwrites
- **Token Usage Tracking**: Reports include input/output token counts for regex and AI scans using tiktoken

## truScanner CLI

![TruScanner Terminal Demo](./truscanner-teminal-demo.gif)

## 📦 Installation

### Prerequisites

- Python 3.9 or higher
- [ollama](https://ollama.com/) (optional, for local AI scanning)
- OpenAI or AWS Bedrock credentials if you want a hosted AI provider

### Quick Install

Using pip:
```bash
pip install truscanner
```

Using uv:
```bash
uv pip install truscanner
```

### Verify installation:
```bash
truscanner --help
```

## 🛠️ Usage

### Basic Usage

Scan a directory with the interactive menu:

```bash
truscanner scan <directory_path>
```

### Example

```bash
truscanner scan ./src
truscanner scan ./my-project
truscanner scan C:\Users\username\projects\my-app
```

### Python API Usage

Use truScanner directly from Python:

```python
import truscanner

# Local path
check = truscanner("/path/to/project")

# file:// URL also works
check = truscanner("file:///Users/username/project")

# Optional explicit call style
check = truscanner.scan("/path/to/project", with_ai=False)

# Run regex and AI scans separately
regex_only = truscanner.scan_regex("/path/to/project")
ai_only = truscanner.scan_ai("/path/to/project", ai_provider="bedrock")

# Run both scans together
full_check = truscanner.scan(
    "/path/to/project",
    with_ai=True,
    ai_provider="openai",
)

# API metadata: total configured catalog size
print(check["configured_data_elements"])
```

Minimal script style:

```python
import truscanner
scan = truscanner("folder_path")
```

Runnable root example:

```bash
python3 simple_truscanner_usage.py ./src
```

Quick smoke check script:

```bash
uv run python scripts/check_truscanner_api.py ./src
```

### Interactive Workflow

1. **Select Output Format**: 
   - Use arrow keys (↑↓) to navigate
   - Press Enter to select
   - Options: `txt`, `md`, `json`, or `All` (generates all three formats)

2. **Scanning Progress**:
   - Real-time progress bar shows file count and percentage
   - Prints configured definition count at start (example: `Loaded data element definitions: 380`)
   - Example: `Scanning: 50/200 (25%) [████████░░░░░░░░░░░░] filename.js`

3. **AI Enhanced Scan (Optional)**:
   - After the regex scan, you'll get a dropdown for the AI-only scan provider:
     `Skip AI scan`, `Ollama`, `OpenAI`, or `AWS Bedrock`
   - This AI pass is separate from the regex scan and is used to find context that regex may miss.
   - If `Ollama` is selected, you can choose the local model from a second dropdown.
   - Live scanning timer: `AI Scanning: filename.js... (5.2s taken)`

4. **Report Generation**:
   - Reports are saved in `reports/{directory_name}/` folder
   - Files are named: `truscan_report.txt`, `truscan_report.md`, `truscan_report.json`
   - Subsequent scans auto-increment: `truscan_report1.txt`, `truscan_report2.txt`, etc.
   - AI findings are saved with `_llm` suffix.

5. **Backend Upload (Optional)**:
   - After reports are saved, you'll be prompted: `Do you want to upload the scan report for the above purpose? (Y, N):`
   - Enter `Y` to upload scan results to backend API
   - View your uploaded scans and analytics at [app.truconsent.io](https://app.truconsent.io/)

### Command Options

```bash
truscanner scan <directory> [OPTIONS]

Options:
  --with-ai          Enable the separate AI scan after the regex scan
  --ai-provider      AI provider: ollama, openai, or bedrock
  --ai-mode          AI scan mode: fast, balanced, or full (default: balanced)
  --personal-only    Only report personal identifiable information (PII)
  --help             Show help message
```

Examples:

```bash
truscanner scan ./src --with-ai --ai-provider openai
truscanner scan ./src --with-ai --ai-provider bedrock
truscanner scan ./src --with-ai --ai-provider ollama
```

### AI Speed vs Coverage Modes

Use `--ai-mode` to control AI scan behavior:

- `fast`: Small prompts, fastest runtime, may skip very large low-signal files
- `balanced` (default): Good speed while keeping broad file coverage
- `full`: Largest context and highest coverage, slowest runtime

Examples:

```bash
truscanner scan ./src --ai-mode fast
truscanner scan ./src --ai-mode balanced
truscanner scan ./src --ai-mode full
```

## 📊 Report Output

### Report Location

Reports are saved in: `reports/{sanitized_directory_name}/`

### Report Formats

- **TXT Report** (`truscan_report.txt`): Plain text format, easy to read
- **Markdown Report** (`truscan_report.md`): Formatted markdown with headers and code blocks
- **JSON Report** (`truscan_report.json`): Structured JSON data for programmatic access

### Report Contents

Each report includes:
- **Scan Report ID**: Unique 32-bit hash identifier
- **Summary**: Configured data elements, distinct detected elements, total findings, and time taken
- **Token Usage**: Input, output, and total token counts for the scan
- **Findings by File**: Detailed list of data elements found in each file
- **Summary by Category**: Aggregated statistics by data category

JSON reports also include:
- `configured_data_elements`
- `distinct_detected_elements`

### Report ID

Each scan generates a unique **Scan Report ID** (32-bit MD5 hash) that:
- Appears in the terminal after scanning
- Is included at the top of all generated report files
- Can be used to track and reference specific scans

## 🔧 Configuration

The `truscanner` package is pre-configured with the live backend URL for seamless scan uploads.

### AI Provider Credentials

`truScanner` loads environment variables from `.env` and from your exported shell environment.

Start by copying the sample file in the repo root:

```bash
cp .env.example .env
```

OpenAI:

```env
OPENAI_KEY=your-openai-key
```

Shell export:

```bash
export OPENAI_KEY=your-openai-key
```

AWS Bedrock:

```env
TRUSCANNER_ACCESS_KEY_ID=your-access-key
TRUSCANNER_SECRET_ACCESS_KEY=your-secret-key
TRUSCANNER_REGION=us-east-1
TRUSCANNER_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
```

Shell export:

```bash
export TRUSCANNER_ACCESS_KEY_ID=your-access-key
export TRUSCANNER_SECRET_ACCESS_KEY=your-secret-key
export TRUSCANNER_REGION=us-east-1
export TRUSCANNER_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
```

Notes:
- If you do not set `TRUSCANNER_MODEL_ID`, `truScanner` defaults to `anthropic.claude-3-haiku-20240307-v1:0`.
- Legacy environment variable names such as `TRUSCANNER_OPENAI_KEY`, `OPENAI_API_KEY`, and `AWS_*` are still accepted as fallback.

## 📁 Project Structure

```
truscanner/
├── src/
│   ├── main.py              # CLI entry point
│   ├── scanner.py           # Regex + AI scan orchestration
│   ├── regex_scanner.py     # Regex/static scanning engine (parallel via ThreadPoolExecutor)
│   ├── ai_scanner.py        # AI scanning orchestration
│   ├── ai_parser.py         # LLM response parsing and validation
│   ├── providers/           # AI provider implementations
│   │   ├── base.py          # Shared progress spinner + response helpers
│   │   ├── ollama.py        # Ollama provider
│   │   ├── openai.py        # OpenAI provider
│   │   └── bedrock.py       # AWS Bedrock provider
│   ├── report_utils.py      # Report file naming utilities
│   └── utils.py             # Env loading, credential helpers, progress display
├── truscanner/              # Public Python API (importable as `import truscanner`)
├── data_elements/           # Privacy data element pattern definitions (JSON)
├── tests/                   # Test suite (pytest)
├── pyproject.toml           # Project configuration and dependencies
└── README.md
```

## 🧪 Development

Install dependencies and run the test suite with [uv](https://github.com/astral-sh/uv):

```bash
uv sync --extra dev
uv run pytest tests/ -v
```

## 📝 Change Policy

For this repository, every code or behavior change must include a matching README update in the same change.

This includes:
- CLI flags, prompts, defaults, scan behavior, output format changes
- Python API changes (`import truscanner`, return schema, parameters)
- Dependency/runtime requirements
- Report format/location updates

## 🤝 Support

For issues, questions, or contributions, please contact: hello@truconsent.io

MIT License - see LICENSE file for details
