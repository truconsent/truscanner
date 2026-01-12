# truScanner

**Open-Source Static Analysis for Privacy Data Flows**

`truScanner` is a static code analysis tool designed to discover data flows in your code. It helps developers and security teams identify where personal data is being processed and maps the journey of that data from collection to destination.

## 🚀 Why truScanner?

Understanding data lineage is critical for privacy and security. `truScanner` automates this by:
- **Discovering PII**: Automatically detecting personal data elements in source code.
- **Reporting**: Generating audit-ready reports.

## ✨ Features

- **Comprehensive Detection**: Identifies more than **110 personal data elements** (e.g., PII, financial data, device identifiers).
- **Multi-Format Reporting**: Produces actionable insights in **Markdown** and **PDF**.

## 📦 Installation

You can install `truScanner` easily using `pip` or `uv`.

### Using pip

```bash
pip install truScanner
```

### Using uv

```bash
uv pip install truScanner
```

## 🛠️ Usage

To scan a project, simply run the `scan` command pointing to your source code directory:

```bash
truScanner scan <path_to_directory>
```

### Example

```bash
truScanner scan ./src
```

## 📊 Output

Upon completion, `truScanner` generates the following reports in your working directory:
- **Markdown Report** (`.md`): Ideal for quick review and integration into version control.
- **PDF Report** (`.pdf`): A polished document suitable for sharing with compliance and security teams.
