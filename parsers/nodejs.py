# Note: This analyzer is non-functional and requires fixing.

from typing import List, Dict
from tree_sitter import Node
from models import APIEndpoint, APIParameter, ParamType
from .base import BaseAnalyzer, execute_query

class NodeJSAnalyzer(BaseAnalyzer):
    """
    Analyzes NodeJS (JavaScript/TypeScript) source code, specifically
    targeting Express.js-style route definitions to extract API endpoints.
    """
    
    def __init__(self, source_bytes: bytes, is_typescript: bool):
        """
        Initializes the analyzer.

        Args:
            source_bytes: The byte content of the source file.
            is_typescript: Flag indicating if the source is TypeScript.
        """
        self.language_name = "typescript" if is_typescript else "javascript"
        super().__init__(source_bytes)

    def analyze(self) -> List[APIEndpoint]:
        """
        Analyzes the source code to find all Express.js-style API endpoints.

        It queries for method calls like `app.get(...)`, `router.post(...)`, etc.
        and extracts the HTTP method, path, and handler details.

        Returns:
            A list of APIEndpoint objects found in the code.
        """
        query = """
        (call_expression
          function: (member_expression
            object: (identifier) @_obj
            property: (property_identifier) @method
          )
          arguments: (arguments) @args
          (#match? @_obj "app|router")
          (#match? @method "get|post|put|delete|patch|use")
        ) @endpoint_node
        """
        
        captures = self._query(query)
        
        endpoints: List[APIEndpoint] = []
        processed_nodes = set()

        node_captures: Dict[int, Dict[str, Node]] = {}
        for node, capture_name in captures:
            endpoint_node = node
            while endpoint_node and endpoint_node.type != "call_expression":
                endpoint_node = endpoint_node.parent
            if not endpoint_node:
                continue

            node_id = endpoint_node.start_byte
            if node_id not in node_captures:
                node_captures[node_id] = {"endpoint_node": endpoint_node}
            
            if capture_name not in node_captures[node_id]:
                 node_captures[node_id][capture_name] = node


        for node_id, data in node_captures.items():
            endpoint_node = data["endpoint_node"]
            method_node = data.get("method")
            args_node = data.get("args")

            if not method_node or not args_node:
                continue

            http_method = self._get_text(method_node).upper()
            
            path = ""
            handler_node = None
            
            arg_children = [child for child in args_node.children if child.is_named]

            for child in arg_children:
                if child.type in ["string_literal", "string"]:
                    path = self._get_text(child).strip("'\"`")
                    break
            
            for child in reversed(arg_children):
                if child.type in ["arrow_function", "function_expression", "identifier"]:
                    handler_node = child
                    break
            
            if not path:
                continue 
            
            handler_name = "unknown_handler"
            if handler_node:
                if handler_node.type == "identifier":
                    handler_name = self._get_text(handler_node)
                else:
                    handler_name = f"anonymous_handler_L{handler_node.start_point[0] + 1}"
            
            endpoints.append(APIEndpoint(
                file_path="", 
                handler_name=handler_name,
                http_method=http_method,
                path=path,
                line_number=endpoint_node.start_point[0] + 1,
                snippet=self._get_text(endpoint_node),
                parameters=self._parse_node_parameters(handler_node, path),
                auth_mechanisms=[]
            ))
        
        return endpoints

    def _parse_node_parameters(self, handler_node: Node, path: str) -> List[APIParameter]:
        """
        Attempts to parse parameters from the route handler and path.

        It extracts path parameters from the path string (e.g., /:id)
        and is intended to scan the handler function for usages of
        `req.query`, `req.params`, and `req.body`.

        Args:
            handler_node: The tree-sitter Node for the handler function.
            path: The endpoint's path string.

        Returns:
            A list of APIParameter objects.
        """
        parameters = []
        if not handler_node:
            return parameters

        for part in path.split('/'):
            if part.startswith(':'):
                param_name = part.lstrip(':')
                parameters.append(APIParameter(
                    name=param_name,
                    param_type=ParamType.PATH,
                    data_type="Any",
                    required=True
                ))

        query = """
        (call_expression
          function: (member_expression
            object: (identifier) @_obj
            property: (property_identifier) @method
          )
          arguments: (arguments) @args
          (#match? @_obj "app|router")
          (#match? @method "get|post|put|delete|patch|use")
        ) @endpoint_node
        """
        captures = execute_query(handler_node, query, self.language_name)
        
        param_map = { "query": ParamType.QUERY, "params": ParamType.PATH, "body": ParamType.BODY }
        found_params = set((p.name, p.param_type) for p in parameters)
        current_type = None

        for node, name in captures:
            text = self._get_text(node)
            if name == "param_type":
                current_type = param_map.get(text)
            elif name == "param_name":
                param_name = text
                if (param_name, current_type) not in found_params:
                    parameters.append(APIParameter(
                        name=param_name,
                        param_type=current_type,
                        data_type="Any", 
                        required=False
                    ))
                    found_params.add((param_name, current_type))

        body_query = """
        (member_expression
          object: (identifier) @req
          property: (property_identifier) @param_type
          (#eq? @req "req")
          (#eq? @param_type "body")
        )
        """
        body_captures = execute_query(handler_node, body_query, self.language_name)
        if body_captures and ("body", ParamType.BODY) not in found_params:
             parameters.append(APIParameter(
                name="body",
                param_type=ParamType.BODY,
                data_type="Object",
                required=False
            ))
             found_params.add(("body", ParamType.BODY))

        return parameters