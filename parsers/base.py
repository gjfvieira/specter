import abc
from typing import List, Dict, Tuple
from tree_sitter import Language, Parser, Node
from tree_sitter_languages import get_language
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

from models import APIEndpoint, APIParameter

_LANGUAGE_CACHE: Dict[str, Language] = {}

def get_ts_language(lang: str) -> Language:
    """
    Retrieves and caches a tree-sitter Language object for performance optimization.
    
    Args:
        lang: Language identifier string (e.g., 'python', 'java')
        
    Returns:
        Cached or newly created tree-sitter Language object
    """
    if lang not in _LANGUAGE_CACHE:
        _LANGUAGE_CACHE[lang] = get_language(lang)
    return _LANGUAGE_CACHE[lang]

def execute_query(node: Node, query_str: str, lang: str) -> List[Tuple[Node, str]]:
    """
    Executes a tree-sitter query against a syntax tree node.
    
    Args:
        node: Tree-sitter Node to query against
        query_str: Query string in tree-sitter query language
        lang: Language identifier string
        
    Returns:
        List of tuples containing matched nodes and their capture names
    """
    language = get_ts_language(lang)
    query = language.query(query_str)
    return query.captures(node)

def get_node_text(node: Node, source_bytes: bytes) -> str:
    """
    Extracts text content from a tree-sitter node with UTF-8 decoding.
    
    Args:
        node: Tree-sitter Node to extract text from
        source_bytes: Raw source code bytes
        
    Returns:
        Decoded text content of the node
    """
    return source_bytes[node.start_byte:node.end_byte].decode('utf8', 'ignore')

class BaseAnalyzer(abc.ABC):
    """
    Abstract base class for language-specific source code analyzers.
    
    This class provides common functionality for parsing source code using tree-sitter
    and extracting API endpoint information. Subclasses must implement the analyze()
    method and set the language_name class attribute.
    
    Attributes:
        language_name: String identifier for the programming language (must be set by subclasses)
        source_bytes: Raw source code bytes to analyze
        parser: Initialized tree-sitter Parser instance
        tree: Parsed syntax tree
        root_node: Root node of the syntax tree
    """
    
    language_name: str = ""

    def __init__(self, source_bytes: bytes):
        """
        Initializes the analyzer with source code and sets up the parser.
        
        Args:
            source_bytes: Raw source code bytes to analyze
            
        Raises:
            ValueError: If subclass hasn't set language_name
        """
        self.source_bytes = source_bytes
        
        if not self.language_name:
            raise ValueError("Subclass must set 'language_name' class attribute")
            
        language = get_ts_language(self.language_name)
        self.parser = Parser()
        self.parser.set_language(language)
        self.tree = self.parser.parse(self.source_bytes)
        self.root_node = self.tree.root_node

    @abc.abstractmethod
    def analyze(self) -> List[APIEndpoint]:
        """
        Analyzes source code to extract API endpoint definitions.
        
        Returns:
            List of discovered APIEndpoint objects
            
        Note:
            Must be implemented by subclasses for language-specific analysis
        """
        pass

    def _query(self, query_str: str) -> List[Tuple[Node, str]]:
        """
        Executes a tree-sitter query on the root node.
        
        Args:
            query_str: Query string in tree-sitter query language
            
        Returns:
            List of matched nodes with their capture names
        """
        return execute_query(self.root_node, query_str, self.language_name)
    
    def _get_text(self, node: Node) -> str:
        """
        Retrieves text content from a syntax tree node.
        
        Args:
            node: Tree-sitter Node to extract text from
            
        Returns:
            Decoded text content of the node
        """
        return get_node_text(node, self.source_bytes)