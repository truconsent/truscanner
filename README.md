# truscanner

**Open-Source Static Analysis for Privacy Data Flows**

`truscanner` is a static code analysis tool designed to discover data flows in your code. It helps developers and security teams identify where personal data is being processed and maps the journey of that data from collection to destination.

## 🚀 Why truscanner?

Understanding data lineage is critical for privacy and security. `truscanner` automates this by:
- **Discovering PII**: Automatically detecting personal data elements in source code.
- **Mapping Flows**: Visualizing how data moves to databases, logs, or third parties.
- **Reporting**: Generating audit-ready reports.

## ✨ Features

- **Comprehensive Detection**: Identifies more than **110 personal data elements** (e.g., PII, financial data, device identifiers).
- **Data Flow Mapping**: Traces data from the point of collection to specific "sinks":
  - ☁️ **External Third Parties**
  - 🗄️ **Databases**
  - 📝 **Logs**
  - 🔗 **Internal APIs**
- **Multi-Format Reporting**: Produces actionable insights in **Markdown** and **PDF**.

## 📦 Installation

You can install `truscanner` easily using `pip` or `uv`.

### Using pip

```bash
pip install truscanner
```

### Using uv

```bash
uv pip install truscanner
```

## 🛠️ Usage

To scan a project, simply run the `scan` command pointing to your source code directory:

```bash
truscanner scan <path_to_directory>
```

### Example

```bash
truscanner scan ./src
```

## 📊 Output

Upon completion, `truscanner` generates the following reports in your working directory:
- **Markdown Report** (`.md`): Ideal for quick review and integration into version control.
- **PDF Report** (`.pdf`): A polished document suitable for sharing with compliance and security teams.