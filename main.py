import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, Tuple
import enum
import typer
from typing_extensions import Annotated
import git
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, TimeRemainingColumn, TaskID

from models import APIEndpoint
from formatters import JsonFormatter, CsvFormatter, MarkdownFormatter, OutputFormatter
from parsers import get_analyzer

console = Console()

app = typer.Typer(
    name="api-scanner",
    help="A CLI tool to analyze source code and extract API endpoint definitions.",
    add_completion=False
)

class LanguageOption(str, enum.Enum):
    """Supported programming language options for analysis."""
    auto = "auto"
    java = "java"
    python = "python"
    nodejs = "nodejs"

class OutputFormat(str, enum.Enum):
    """Supported output format options."""
    json = "json"
    csv = "csv"
    md = "md"

def get_language_from_extension(file_path: Path, force_language: LanguageOption) -> Optional[str]:
    """
    Determines the programming language based on file extension or forced language option.
    
    Args:
        file_path: Path to the source file
        force_language: Language to force, if not auto-detect
        
    Returns:
        String identifier of the programming language or None if not supported
    """
    if force_language != LanguageOption.auto:
        if force_language == LanguageOption.nodejs:
            if file_path.suffix in ['.js', '.ts']:
                return 'typescript' if file_path.suffix == '.ts' else 'javascript'
            return None
        return force_language.value
    ext_map = {
        ".py": "python",
        ".java": "java",
        ".js": "javascript",
        ".ts": "typescript",
    }
    return ext_map.get(file_path.suffix.lower())

def split_by_comma(ext: Optional[List[str]]) -> List[str]:
    """
    Splits and normalizes a comma-separated string into a list.
    
    Args:
        ext: String to split or list of strings
        
    Returns:
        List of normalized, lowercase strings
    """
    if ext is None:
        return []
    if isinstance(ext, str):
        return [i.strip().lower() for i in ext.split(",") if i.strip()]
    return [i.strip().lower() for i in ext]

def split_paths(paths_str: Optional[str]) -> List[str]:
    """
    Splits a semicolon-separated string of paths into normalized paths.
    
    Args:
        paths_str: Semicolon-separated string of paths
        
    Returns:
        List of normalized path strings
    """
    if not paths_str:
        return []
    return [
        p.strip().replace("\\", "/")
        for p in paths_str.split(";")
        if p.strip()
    ]

@app.command()
def scan(
    source_path: Annotated[str, typer.Argument(help="The path to a local directory or a Git repository URL to scan.")],
    output_format: Annotated[OutputFormat, typer.Option("--format", "-f", help="The desired output format.")] = OutputFormat.md,
    output_file: Annotated[Optional[Path], typer.Option("--output", "-o", help="Path to the output file. Prints to console if not provided.")] = None,
    path_filter: Annotated[Optional[str], typer.Option("--path-filter", "-p", help="Only analyze files within this specific sub-path.")] = None,
    language: Annotated[LanguageOption, typer.Option("--lang", "-l", help="Force language detection instead of relying on file extensions.")] = LanguageOption.auto,
    ext: Annotated[Optional[str], typer.Option("--ext", "-e", help="File extensions to include (comma-separated, e.g. 'py,java,js').")] = None,
    exclude_ext: Annotated[Optional[str], typer.Option("--exclude-ext", help="File extensions to ignore (comma-separated, e.g. 'test,md').")] = None,
    include_verbs: Annotated[Optional[str], typer.Option("--include-verbs", help="Only include endpoints with these HTTP verbs (comma-separated, e.g. 'GET,POST').")] = None,
    exclude_verbs: Annotated[Optional[str], typer.Option("--exclude-verbs", help="Exclude endpoints with these HTTP verbs (comma-separated, e.g. 'DELETE,PATCH').")] = None,
    auth: Annotated[bool, typer.Option("--auth", is_flag=True, help="Only show authenticated endpoints.")] = False,
    no_auth: Annotated[bool, typer.Option("--no-auth", is_flag=True, help="Only show non-authenticated endpoints.")] = False,
    ignore_paths: Annotated[Optional[str], typer.Option("--ignore-paths", help="Semicolon-separated list of path prefixes to ignore (e.g., 'src/test;target').")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", is_flag=True, help="Enable verbose logging, showing each file being analyzed.")] = False,
):
    """
    Analyzes source code to extract API endpoint definitions with various filtering options.
    
    Supports local directories and Git repositories as input sources. Can analyze multiple
    programming languages and output results in different formats. Provides filtering options
    for HTTP verbs, authentication requirements, and specific paths.
    
    The analysis process includes:
    1. Source code retrieval (local or git clone)
    2. File scanning and language detection
    3. API endpoint extraction
    4. Filtering based on provided criteria
    5. Output formatting and display/save
    
    Args:
        source_path: Path to analyze (local directory or git URL)
        output_format: Desired output format (json, csv, markdown)
        output_file: Optional file to save results
        path_filter: Optional path to limit analysis scope
        language: Programming language to force
        ext: File extensions to include
        exclude_ext: File extensions to exclude
        include_verbs: HTTP verbs to include
        exclude_verbs: HTTP verbs to exclude
        auth: Filter for authenticated endpoints
        no_auth: Filter for non-authenticated endpoints
        ignore_paths: Paths to ignore
        verbose: Enable verbose output
    """
    
    if auth and no_auth:
        console.print("[bold red]Error:[/bold red] --auth and --no-auth are mutually exclusive.")
        raise typer.Exit(code=1)
        
    is_git_url = source_path.startswith(('http://', 'https://', 'git@'))
    if is_git_url:
        temp_dir = tempfile.mkdtemp()
        console.print(f"Cloning repository from [cyan]{source_path}[/cyan] into temporary directory...")
        try:
            git.Repo.clone_from(source_path, temp_dir)
            repo_path = Path(temp_dir)
        except git.GitCommandError as e:
            console.print(f"[bold red]Error:[/bold red] Failed to clone repository: {e}")
            shutil.rmtree(temp_dir)
            raise typer.Exit(code=1)
    else:
        repo_path = Path(source_path)
        if not repo_path.is_dir():
            console.print(f"[bold red]Error:[/bold red] Local path '{source_path}' is not a valid directory.")
            raise typer.Exit(code=1)
        temp_dir = None # Not a temporary directory, don't delete

    try:
        analysis_path = repo_path
        if path_filter:
            analysis_path = repo_path / path_filter
        if not analysis_path.exists():
            console.print(f"[bold red]Error:[/bold red] Path filter '{path_filter}' does not exist in the repository.")
            raise typer.Exit(code=1)

        include_exts = set(split_by_comma(ext))
        exclude_exts = set(split_by_comma(exclude_ext))
        ignored_paths_set = set(split_paths(ignore_paths))

        all_endpoints: List[APIEndpoint] = []
        files_analyzed_count = 0

        # --- PRE-SCAN FOR PROGRESS BAR (only if not verbose) ---
        files_to_analyze: List[Tuple[Path, str]] = []
        lang_counts: Dict[str, int] = {}
        if not verbose:
            console.print("Pre-scanning repository to count files...")
            for root, _, files in os.walk(analysis_path):
                for filename in files:
                    file_path = Path(root) / filename
                    relative_file_path = str(file_path.relative_to(repo_path)).replace("\\", "/")

                    if any(relative_file_path.startswith(p) for p in ignored_paths_set):
                        continue

                    file_ext = file_path.suffix.lstrip('.').lower()
                    if include_exts and file_ext not in include_exts:
                        continue
                    if exclude_exts and file_ext in exclude_exts:
                        continue

                    lang = get_language_from_extension(file_path, language)
                    if lang:
                        files_to_analyze.append((file_path, lang))
                        lang_counts[lang] = lang_counts.get(lang, 0) + 1
            console.print(f"Found {len(files_to_analyze)} files to analyze across {len(lang_counts)} language(s).")
        # --- END PRE-SCAN ---

        # --- Main Processing Logic ---
        if verbose:
            # --- VERBOSE MODE (Original behavior) ---
            console.print("Starting analysis (verbose mode)...")
            for root, _, files in os.walk(analysis_path):
                for filename in files:
                    file_path = Path(root) / filename
                    relative_file_path = str(file_path.relative_to(repo_path)).replace("\\", "/")

                    if any(relative_file_path.startswith(p) for p in ignored_paths_set):
                        continue

                    file_ext = file_path.suffix.lstrip('.').lower()
                    if include_exts and file_ext not in include_exts:
                        continue
                    if exclude_exts and file_ext in exclude_exts:
                        continue

                    lang = get_language_from_extension(file_path, language)
                    if lang:
                        try:
                            with open(file_path, 'rb') as f:
                                source_bytes = f.read()
                            analyzer = get_analyzer(lang, source_bytes)
                            if analyzer:
                                files_analyzed_count += 1
                                # The verbose print:
                                console.print(f" -> Analyzing [green]{relative_file_path}[/green] as {lang}")
                                endpoints = analyzer.analyze()
                                for endpoint in endpoints:
                                    endpoint.file_path = relative_file_path
                                all_endpoints.extend(endpoints)
                        except Exception as e:
                            # Still print warnings in verbose mode
                            console.print(f"[yellow]Warning:[/yellow] Could not analyze file {file_path}: {e}")
        else:
            # --- QUIET MODE (Progress Bar) ---
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                "[progress.percentage]{task.percentage:>3.0f}%",
                "({task.completed} of {task.total})",
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                
                main_task = progress.add_task("[cyan]Overall Progress", total=len(files_to_analyze))
                
                lang_tasks: Dict[str, TaskID] = {}
                for lang, count in sorted(lang_counts.items()):
                    task_id = progress.add_task(f"  [green]{lang.capitalize()}", total=count)
                    lang_tasks[lang] = task_id

                for file_path, lang in files_to_analyze:
                    relative_file_path = str(file_path.relative_to(repo_path)).replace("\\", "/")
                    try:
                        with open(file_path, 'rb') as f:
                            source_bytes = f.read()
                        analyzer = get_analyzer(lang, source_bytes)
                        if analyzer:
                            files_analyzed_count += 1
                            endpoints = analyzer.analyze()
                            for endpoint in endpoints:
                                endpoint.file_path = relative_file_path
                            all_endpoints.extend(endpoints)
                    except Exception as e:
                        # Print warnings ABOVE the progress bar
                        progress.log(f"[yellow]Warning:[/yellow] Could not analyze file {file_path}: {e}")
                    
                    # Update progress bars
                    progress.update(main_task, advance=1)
                    if lang in lang_tasks:
                        progress.update(lang_tasks[lang], advance=1)

        console.print(f"\nAnalysis complete. Analyzed {files_analyzed_count} files and found {len(all_endpoints)} potential endpoints.")

        # --- Filtering Logic ---
        if any([include_verbs, exclude_verbs, auth, no_auth]):
            console.print("Applying filters...")
            filtered_endpoints: List[APIEndpoint] = []
            
            include_set = set(v.strip().upper() for v in include_verbs.split(',')) if include_verbs else set()
            exclude_set = set(v.strip().upper() for v in exclude_verbs.split(',')) if exclude_verbs else set()

            for endpoint in all_endpoints:
                verb = endpoint.http_method.upper()
                if include_set and verb not in include_set:
                    continue
                if exclude_set and verb in exclude_set:
                    continue
                
                is_authenticated = bool(endpoint.auth_mechanisms)
                if auth and not is_authenticated:
                    continue 
                if no_auth and is_authenticated:
                    continue
                
                filtered_endpoints.append(endpoint)
            
            console.print(f" -> {len(all_endpoints) - len(filtered_endpoints)} endpoints filtered out. {len(filtered_endpoints)} remaining.")
            all_endpoints = filtered_endpoints
        # --- End of Filtering Logic ---

        formatter: OutputFormatter
        if output_format == OutputFormat.json:
            formatter = JsonFormatter()
        elif output_format == OutputFormat.csv:
            formatter = CsvFormatter()
        else:
            formatter = MarkdownFormatter()
        
        formatted_output = formatter.format(all_endpoints)

        # Write output
        if output_file:
            try:
                output_file.write_text(formatted_output, encoding='utf-8')
                console.print(f"\nResults saved to [cyan]{output_file}[/cyan]")
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] Could not write to output file {output_file}: {e}")
                raise typer.Exit(code=1)
        else:
            console.print("\n--- Analysis Results ---")
            if output_format == OutputFormat.md:
                from rich.markdown import Markdown as RichMarkdown
                console.print(RichMarkdown(formatted_output))
            else:
                console.print(formatted_output)
    finally:
        if is_git_url and temp_dir:
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    app()