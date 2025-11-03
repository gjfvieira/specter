from typing import Optional
from .base import BaseAnalyzer
from .python import PythonAnalyzer
from .java import JavaAnalyzer
from .nodejs import NodeJSAnalyzer

def get_analyzer(language: str, source_bytes: bytes) -> Optional[BaseAnalyzer]:
    """Factory function to get the correct analyzer for a language."""
    if language == 'python':
        return PythonAnalyzer(source_bytes)
    if language == 'java':
        return JavaAnalyzer(source_bytes)
    if language == 'javascript':
        return NodeJSAnalyzer(source_bytes, is_typescript=False)
    if language == 'typescript':
        return NodeJSAnalyzer(source_bytes, is_typescript=True)
    return None