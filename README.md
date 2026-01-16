# truScanner

**Open-Source Static Analysis for Privacy Data Flows**

`truScanner` is a static code analysis tool designed to discover and analyze personal data elements in your source code. It helps developers and security teams identify privacy-related data flows and generate comprehensive reports.

## 🚀 Features

- **Comprehensive Detection**: Identifies 110+ personal data elements (PII, financial data, device identifiers, etc.)
- **Interactive Menu**: Arrow-key navigable menu for selecting output formats
- **Real-time Progress**: Visual progress indicator during scanning
- **Multiple Report Formats**: Generate reports in TXT, Markdown, or JSON format
- **Backend Integration**: Optional upload to backend API for centralized storage
- **Auto-incrementing Reports**: Automatically manages report file naming to prevent overwrites

## 📦 Installation

### Prerequisites

- Python 3.9 or higher
- pip or uv package manager

### Install from Source

1. **Clone or navigate to the truscanner directory**:
   ```bash
   cd truscanner
   ```

2. **Install dependencies**:
   
   Using pip:
   ```bash
   pip install -r requirements.txt
   ```
   
   Or using uv:
   ```bash
   uv pip install -e .
   ```

3. **Verify installation**:
   ```bash
   truScanner --help
   ```

## 🛠️ Usage

### Basic Usage

Scan a directory with the interactive menu:

```bash
truScanner scan <directory_path>
```

### Example

```bash
truScanner scan ./src
truScanner scan ./my-project
truScanner scan C:\Users\username\projects\my-app
```

### Interactive Workflow

1. **Select Output Format**: 
   - Use arrow keys (↑↓) to navigate
   - Press Enter to select
   - Options: `txt`, `md`, `json`, or `All` (generates all three formats)

2. **Scanning Progress**:
   - Real-time progress bar shows file count and percentage
   - Example: `Scanning: 50/200 (25%) [████████░░░░░░░░░░░░] filename.js`

3. **Report Generation**:
   - Reports are saved in `Reports/{directory_name}/` folder
   - Files are named: `truscan_report.txt`, `truscan_report.md`, `truscan_report.json`
   - Subsequent scans auto-increment: `truscan_report1.txt`, `truscan_report2.txt`, etc.

4. **Backend Upload (Optional)**:
   - After reports are saved, you'll be prompted: `Do you want to analyze? (Y/n):`
   - Enter `Y` to upload scan results to backend API
   - Requires `TRUSCANNER_BACKEND_URL` in environment variables

### Command Options

```bash
truScanner scan <directory> [OPTIONS]

Options:
  --with-presidio    Enable Presidio NLP scanner (requires model download)
  --with-ai          Enable AI/LLM scanner (requires OPENAI_API_KEY)
  --personal-only    Only report personal identifiable information (PII)
  --help             Show help message
```

### Examples with Options

```bash
# Scan with only PII data
truScanner scan ./src --personal-only

# Scan with Presidio NLP scanner
truScanner scan ./src --with-presidio

# Scan with AI/LLM scanner
truScanner scan ./src --with-ai
```

## 📊 Report Output

### Report Location

Reports are saved in: `Reports/{sanitized_directory_name}/`

### Report Formats

- **TXT Report** (`truscan_report.txt`): Plain text format, easy to read
- **Markdown Report** (`truscan_report.md`): Formatted markdown with headers and code blocks
- **JSON Report** (`truscan_report.json`): Structured JSON data for programmatic access

### Report Contents

Each report includes:
- **Scan Report ID**: Unique 32-bit hash identifier
- **Summary**: Total findings, time taken, files scanned
- **Findings by File**: Detailed list of data elements found in each file
- **Summary by Category**: Aggregated statistics by data category

### Report ID

Each scan generates a unique **Scan Report ID** (32-bit MD5 hash) that:
- Appears in the terminal after scanning
- Is included at the top of all generated report files
- Can be used to track and reference specific scans

## 🔧 Configuration

## 🔧 Configuration

The `truscanner` package is pre-configured with the live backend URL for seamless scan uploads. No additional configuration is required.

## 📁 Project Structure

```
truscanner/
├── src/
│   ├── main.py              # CLI entry point
│   ├── regex_scanner.py     # Core scanning engine
│   ├── report_utils.py      # Report utilities
│   └── utils.py             # Interactive menu & backend integration
├── data_elements/           # Data element definitions (JSON files)
├── Reports/                 # Generated reports (created automatically)
├── requirements.txt         # Python dependencies
└── README.md
```

## 🐛 Troubleshooting

### Interactive Menu Not Working

If the arrow-key menu doesn't appear, ensure `inquirer` is installed:
```bash
pip install inquirer
```

### Backend Upload Fails

- Verify network connectivity to the internet
- Check if the backend server is currently under maintenance

### No Reports Generated

- Ensure you have write permissions in the current directory
- Check that the directory you're scanning contains readable files
- Verify Python version is 3.9 or higher

## 📝 License

MIT License - see LICENSE file for details

## 🤝 Support

For issues, questions, or contributions, please contact: hello@truconsent.io
