# Note: This analyzer is non-functional and requires fixing.

from typing import List, Dict
from tree_sitter import Node
from models import APIEndpoint, APIParameter, ParamType
from .base import BaseAnalyzer, execute_query

class PythonAnalyzer(BaseAnalyzer):
    """
    Analyzes Python source code, specifically targeting FastAPI decorators
    (e.g., @app.get(...)) to extract API endpoint definitions.
    """
    language_name = "python"

    def __init__(self, source_bytes: bytes):
        """
        Initializes the analyzer with the source code bytes.

        Args:
            source_bytes: The byte content of the Python source file.
        """
        super().__init__(source_bytes)

    def analyze(self) -> List[APIEndpoint]:
        """
        Analyzes the Python source code to find all FastAPI endpoints.

        It queries for decorator nodes (@app.get, @app.post, etc.),
        finds the function they are attached to, and extracts the
        HTTP method, path, handler name, and parameters.

        Returns:
            A list of APIEndpoint objects found in the code.
        """
        query = """
        (decorator
          (call
            function: (attribute
              object: (identifier) @app
              attribute: (identifier) @method
            )
            arguments: (argument_list
              (string) @path
            )
          )
          (#match? @method "get|post|put|delete|patch|route")
        ) @decorator_node
        """
        
        captures = self._query(query)
        
        endpoints_map: Dict[str, APIEndpoint] = {}
        processed_nodes = set()

        for node, capture_name in captures:
            decorator_node = node
            while decorator_node and decorator_node.type != "decorator":
                decorator_node = decorator_node.parent
            if not decorator_node or decorator_node.id in processed_nodes:
                continue

            endpoint_node = decorator_node.parent
            if endpoint_node.type != "function_definition":
                 if endpoint_node.parent and endpoint_node.parent.type == "function_definition":
                     endpoint_node = endpoint_node.parent
                 else:
                     continue 

            processed_nodes.add(decorator_node.id)

            handler_name_node = endpoint_node.child_by_field_name("name")
            if not handler_name_node:
                continue
            
            handler_name = self._get_text(handler_name_node)
            
            if handler_name not in endpoints_map:
                params_node = endpoint_node.child_by_field_name("parameters")
                endpoints_map[handler_name] = APIEndpoint(
                    file_path="", 
                    handler_name=handler_name,
                    http_method="",
                    path="",
                    line_number=endpoint_node.start_point[0] + 1,
                    snippet=self._get_text(endpoint_node),
                    parameters=self._parse_python_parameters(params_node),
                    auth_mechanisms=[] 
                )
            
            endpoint = endpoints_map[handler_name]

            local_captures = self._query(query)
            for n, name in local_captures:
                current_decorator = n
                while current_decorator and current_decorator.id != decorator_node.id:
                    current_decorator = current_decorator.parent
                
                if current_decorator: 
                    text = self._get_text(n)
                    if name == "method":
                        endpoint.http_method = text.upper()
                    elif name == "path":
                        endpoint.path = text.strip("'\"")

        return list(endpoints_map.values())

    def _parse_python_parameters(self, params_node: Node) -> List[APIParameter]:
        """
        Parses parameters from a Python function's (parameters) node.

        It identifies parameter names, type hints, and default values
        to determine the parameter's details.

        Args:
            params_node: The tree-sitter Node for the function's parameters.

        Returns:
            A list of APIParameter objects.
        """
        parameters = []
        if not params_node:
            return parameters

        query = """
        [
            (typed_parameter
                (identifier) @param_name
                type: (type (identifier) @param_type)
            ) @param_node
            
            (default_parameter
                name: (identifier) @param_name
                type: (type (identifier) @param_type)
                value: (_) @default_value
            ) @param_node
            
            (default_parameter
                name: (identifier) @param_name
                value: (_) @default_value
            ) @param_node
            
            (identifier) @param_name
        ]
        """
        
        captures = execute_query(params_node, query, self.language_name)

        current_param_node_id = None
        current_param = {}

        for node, name in captures:
            param_node = node
            while param_node and param_node.type not in ["typed_parameter", "default_parameter", "identifier"]:
                param_node = param_node.parent
            if not param_node:
                continue
                
            if param_node.type == "identifier" and name == "param_name":
                if param_node.start_byte != current_param_node_id:
                    if "name" in current_param:
                         parameters.append(self._create_python_parameter(current_param))
                    current_param_node_id = param_node.start_byte
                    current_param = {"node": param_node, "required": True, "name": self._get_text(node)}
                continue

            if current_param_node_id != param_node.start_byte:
                if "name" in current_param:
                    parameters.append(self._create_python_parameter(current_param))
                current_param_node_id = param_node.start_byte
                current_param = {"node": param_node, "required": True}
                if param_node.type == "default_parameter":
                    current_param["required"] = False


            text = self._get_text(node)
            if name == "param_name":
                current_param["name"] = text
            elif name == "param_type":
                current_param["type"] = text
            elif name == "default_value":
                current_param["required"] = False
                current_param["default"] = text
        
        if "name" in current_param:
            parameters.append(self._create_python_parameter(current_param))

        return parameters

    def _create_python_parameter(self, param_data: dict) -> APIParameter:
        """
        Creates an APIParameter, determining its type (Path, Query, Body)
        based on FastAPI conventions (e.g., default values, type hints).

        Args:
            param_data: A dictionary containing extracted parameter info
                        (name, type, default, required).

        Returns:
            An APIParameter object.
        """
        param_type = ParamType.QUERY 
        data_type = param_data.get("type", "Any")
        default_val = param_data.get("default", "")

        if default_val.startswith("Path("):
            param_type = ParamType.PATH
            param_data["required"] = "..." not in default_val
        elif default_val.startswith("Query("):
            param_type = ParamType.QUERY
            param_data["required"] = "..." not in default_val
        elif default_val.startswith("Body("):
            param_type = ParamType.BODY
            param_data["required"] = "..." not in default_val
        elif not param_data["required"]:
             param_type = ParamType.QUERY 
        else:
            if data_type.lower() in ["int", "str", "float", "bool", "any"]:
                param_type = ParamType.QUERY 
            else:
                param_type = ParamType.BODY 

        return APIParameter(
            name=param_data["name"],
            param_type=param_type,
            data_type=data_type,
            required=param_data["required"]
        )