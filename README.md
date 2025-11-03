# Specter Scanner

Specter is a CLI tool designed to analyze source code repositories (local or Git) to find and extract API endpoint definitions. It uses `tree-sitter` to parse code and identify endpoint patterns in various languages, exporting the findings into multiple formats.

-----

## 🚨 Important: Project Status & Known Issues

This project is a **work-in-progress** and was created using **vibe coding**. Several key components are not functional and require fixing.

  * 🔴 **Python Parser (`parsers/python.py`): Non-functional.** This parser is incomplete and does not correctly identify endpoints. It needs to be fixed.
  * 🔴 **NodeJS Parser (`parsers/nodejs.py`): Non-functional.** This parser is also incomplete and requires a fix to work.
  * 🟡 **Java Parser (`parsers/java.py`): Partially functional.** This parser works for simple queries (e.g., basic Spring Boot `@GetMapping` annotations). It does **not** currently export advanced or "encapsulated" endpoints (e.g., complex nested routing or configurations).

-----

## Features

  * **Source Scanning:** Analyzes local directories or automatically clones remote Git repositories.
  * **Multi-Language (in theory):** Built with a factory to support Java, Python, and NodeJS.
  * **Multiple Formats:** Exports findings as a Markdown table, JSON, or CSV.
  * **Rich Output:** Uses `rich` for clean console output and progress bars.
  * **Filtering:** Allows filtering by sub-paths, included/excluded HTTP verbs, and authentication status.

## Installation

1.  Clone this repository:

    ```bash
    git clone <your-repo-url>
    cd specter-project
    ```

2.  Create and activate a virtual environment (recommended):

    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```

3.  Install the required dependencies:

    ```bash
    pip install -r specter/requirements.txt
    ```

## Usage

The tool is run via `specter/main.py`. The main command is `scan`.

```bash
python specter/main.py scan [OPTIONS] SOURCE_PATH
```

### Examples

**Scan a local Java project and print results to the console:**

```bash
python specter/main.py scan /path/to/my-java-project --lang java
```

**Scan a remote Git repository and save the results as a Markdown file:**

```bash
python specter/main.py scan https://github.com/user/my-repo.git \
       --format md \
       --output results.md
```

**Scan a project, only showing `GET` and `POST` endpoints:**

```bash
python specter/main.py scan /path/to/project \
       --include-verbs "GET,POST"
```

### Key Options

  * `SOURCE_PATH`: The local directory or Git URL to scan.
  * `--format, -f`: Output format (`json`, `csv`, `md`). Default is `md`.
  * `--output, -o`: Path to the output file. Prints to console if not provided.
  * `--lang, -l`: Force a specific language (`auto`, `java`, `python`, `nodejs`). Default is `auto`.
  * `--include-verbs`: Only include endpoints with these HTTP verbs (comma-separated, e.g., "GET,POST").
  * `--exclude-verbs`: Exclude endpoints with these HTTP verbs (comma-separated, e.g., "DELETE,PATCH").
  * `--ignore-paths`: Semicolon-separated list of path prefixes to ignore (e.g., 'src/test;target').
  * `--verbose, -v`: Enable verbose logging to see each file being analyzed.