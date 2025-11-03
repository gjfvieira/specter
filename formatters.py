import abc
import csv
import io
import json
from typing import List
from models import APIEndpoint, ParamType, APIParameter

def _format_parameters_md(params: List[APIParameter]) -> str:
    """
    Formats a list of API parameters into Markdown representation.
    
    Args:
        params: List of APIParameter objects to format
        
    Returns:
        Formatted string with parameters grouped by type, separated by HTML line breaks
    """
    if not params:
        return "None"
    
    parts = []
    for param_type in ParamType:
        typed_params = [p for p in params if p.param_type == param_type]
        if typed_params:
            names = ", ".join([p.name for p in typed_params])
            parts.append(f"<b>{param_type.value.capitalize()}:</b> {names}")
            
    return "<br>".join(parts)

def _format_parameters_csv(params: List[APIParameter]) -> str:
    """
    Formats a list of API parameters into CSV representation.
    
    Args:
        params: List of APIParameter objects to format
        
    Returns:
        Space-separated string of parameter groups
    """
    if not params:
        return "None"
    
    parts = []
    for param_type in ParamType:
        typed_params = [p for p in params if p.param_type == param_type]
        if typed_params:
            names = ", ".join([p.name for p in typed_params])
            parts.append(f"{param_type.value.capitalize()}: {names}")
            
    return " ".join(parts)

def _format_parameters_json(params: List[APIParameter]) -> dict:
    """
    Formats a list of API parameters into JSON structure.
    
    Args:
        params: List of APIParameter objects to format
        
    Returns:
        Dictionary with parameter types as keys and comma-separated parameter names as values
    """
    param_obj = {
        "path": None,
        "query": None,
        "body": None,
        "header": None,
        "cookie": None
    }
    
    if not params:
        return param_obj
        
    for param_type in ParamType:
        typed_params = [p.name for p in params if p.param_type == param_type.value]
        if typed_params:
            param_obj[param_type.value] = ", ".join(typed_params)
            
    return param_obj

def _format_auth(auth_mechanisms: List[str]) -> str:
    """
    Formats authentication mechanisms into a simple yes/no/unknown string.
    
    Args:
        auth_mechanisms: List of authentication mechanism identifiers
        
    Returns:
        "Yes" if mechanisms exist, "Unknown" if empty
    """
    if not auth_mechanisms:
        return "Unknown"
    return "Yes"

def _format_location(endpoint: APIEndpoint) -> str:
    """
    Formats the source code location of an endpoint.
    
    Args:
        endpoint: APIEndpoint object containing location information
        
    Returns:
        String in format "file_path:line_number"
    """
    return f"{endpoint.file_path}:{endpoint.line_number}"

def _clean_for_csv(text: str) -> str:
    """
    Sanitizes text for CSV output by removing problematic characters.
    
    Args:
        text: String to clean
        
    Returns:
        Sanitized string with pipes and newlines removed
    """
    return str(text).replace('|', '').replace('\n', ' ').replace('\r', ' ')

class OutputFormatter(abc.ABC):
    """Abstract base class defining the interface for endpoint formatters."""
    
    @abc.abstractmethod
    def format(self, endpoints: List[APIEndpoint]) -> str:
        """
        Formats a list of endpoints into a string representation.
        
        Args:
            endpoints: List of APIEndpoint objects to format
            
        Returns:
            Formatted string representation
        """
        pass

class JsonFormatter(OutputFormatter):
    """Formats API endpoints as JSON with standardized structure."""
    
    def format(self, endpoints: List[APIEndpoint]) -> str:
        """
        Formats endpoints as a JSON string with indentation.
        
        Args:
            endpoints: List of APIEndpoint objects to format
            
        Returns:
            Formatted JSON string
        """
        output_data = []
        for e in endpoints:
            output_data.append({
                "Endpoint": e.path,
                "Method": e.http_method,
                "Parameters": _format_parameters_json(e.parameters),
                "Authentication": _format_auth(e.auth_mechanisms),
                "Location": _format_location(e),
                "Snippet": e.snippet
            })
        return json.dumps(output_data, indent=2)

class CsvFormatter(OutputFormatter):
    """Formats API endpoints as pipe-delimited CSV."""
    
    def format(self, endpoints: List[APIEndpoint]) -> str:
        """
        Formats endpoints as pipe-delimited CSV string.
        
        Args:
            endpoints: List of APIEndpoint objects to format
            
        Returns:
            CSV string with pipe delimiter
        """
        output = io.StringIO()
        writer = csv.writer(output, delimiter='|')

        writer.writerow([
            "Endpoint", "Method", "Parameters", "Authentication", "Location", "Snippet"
        ])

        for e in endpoints:
            writer.writerow([
                _clean_for_csv(e.path),
                _clean_for_csv(e.http_method),
                _clean_for_csv(_format_parameters_csv(e.parameters)),
                _clean_for_csv(_format_auth(e.auth_mechanisms)),
                _clean_for_csv(_format_location(e)),
                _clean_for_csv(e.snippet)
            ])

        return output.getvalue()

class MarkdownFormatter(OutputFormatter):
    """Formats API endpoints as a Markdown table."""
    
    def format(self, endpoints: List[APIEndpoint]) -> str:
        """
        Formats endpoints as a Markdown table string.
        
        Args:
            endpoints: List of APIEndpoint objects to format
            
        Returns:
            Markdown table string with headers and aligned columns
        """
        md = []
        
        md.append("| Endpoint | Method | Parameters | Authentication | Location | Snippet |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        
        sorted_endpoints = sorted(endpoints, key=lambda e: (e.file_path, e.line_number))

        for e in sorted_endpoints:
            snippet_md = f"<code>{e.snippet.replace('|', '&#124;').replace('\n', '<br>')}</code>"
            location_md = f"[{_format_location(e)}]"
            
            md.append(f"| {e.path} | {e.http_method} | {_format_parameters_md(e.parameters)} | {_format_auth(e.auth_mechanisms)} | {location_md} | {snippet_md} |")
        
        return "\n".join(md)