# Note: This analyzer is a work in progress and currently supports
# basic endpoint detection. More advanced search features are planned.

from typing import List, Dict
from tree_sitter import Node
from models import APIEndpoint, APIParameter, ParamType
from .base import BaseAnalyzer, execute_query

class JavaAnalyzer(BaseAnalyzer):
    """
    Analyzes Java source code (specifically Spring Boot and JAX-RS)
    to extract API endpoint definitions.
    """
    language_name = "java"

    def __init__(self, source_bytes: bytes):
        """
        Initializes the analyzer with the source code bytes.

        Args:
            source_bytes: The byte content of the Java source file.
        """
        super().__init__(source_bytes)

    def analyze(self) -> List[APIEndpoint]:
        """
        Analyzes the Java source code to find all API endpoints.

        It queries for class declarations, processes each class to find
        a base path and class-level auth, and then scans its methods
        for endpoint definitions.

        Returns:
            A list of APIEndpoint objects found in the code.
        """
        endpoints = []
        
        class_query = """
            (class_declaration) @class_node
        """
        
        class_captures = self._query(class_query)
        processed_class_nodes = set()

        for class_node, capture_name in class_captures:
            if capture_name == "class_node" and class_node.start_byte not in processed_class_nodes:
                processed_class_nodes.add(class_node.start_byte)
                
                base_path = self._find_class_base_path(class_node)
                class_auth = self._find_class_auth(class_node)
                class_body = next((c for c in class_node.children if c.type == 'class_body'), None)
                
                if class_body:
                    endpoints.extend(self._find_methods(class_body, base_path, class_auth))
        return endpoints

    def _find_class_base_path(self, class_node: Node) -> str:
        """
        Finds the base path defined on a class via @RequestMapping or @Path.

        Args:
            class_node: The tree-sitter Node for the class declaration.

        Returns:
            The base path string if found, otherwise an empty string.
        """
        query = """
        [
            (annotation
                name: (identifier) @anno_name
                arguments: (annotation_argument_list) @args
            )
            (marker_annotation
                name: (identifier) @anno_name
            )
        ] @annotation_node
        """
        modifiers = next((c for c in class_node.children if c.type == 'modifiers'), None)
        if not modifiers:
            return ""
        
        captures = execute_query(modifiers, query, self.language_name)
        
        annot_nodes = {}
        for node, name in captures:
            annot_node = node
            while annot_node and annot_node.type not in ['annotation', 'marker_annotation']:
                annot_node = annot_node.parent
            if annot_node:
                annot_nodes.setdefault(annot_node.start_byte, {})[name] = node

        for data in annot_nodes.values():
            if "anno_name" in data:
                annot = self._get_text(data["anno_name"])
                if annot in ["RequestMapping", "Path"]:
                    if "args" in data:
                        literals = self._collect_string_literals(data["args"])
                        return literals[0] if literals else ""
        return ""

    @staticmethod
    def _collect_string_literals(node: Node) -> List[str]:
        """
        Recursively collects all string literals from a given node.

        Args:
            node: The tree-sitter Node to start the search from.

        Returns:
            A list of string values found.
        """
        literals = []
        if node and node.type == "string_literal":
            literals.append(node.text.decode("utf-8").strip('"'))
        elif node:
            for child in node.children:
                literals.extend(JavaAnalyzer._collect_string_literals(child))
        return literals

    def _find_methods(self, class_body: Node, base_path: str, class_auth: List[str]) -> List[APIEndpoint]:
        """
        Scans a class body for methods annotated as API endpoints.

        Args:
            class_body: The tree-sitter Node for the class_body.
            base_path: The base path inherited from the class.
            class_auth: A list of auth mechanisms inherited from the class.

        Returns:
            A list of APIEndpoint objects found in the class body.
        """
        method_mappings = {
            "GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
            "DeleteMapping": "DELETE", "PatchMapping": "PATCH", "RequestMapping": "ANY",
            "GET": "GET", "POST": "POST", "PUT": "PUT", "DELETE": "DELETE", "PATCH": "PATCH",
        }
        
        path_annotations = {
            "RequestMapping", "GetMapping", "PostMapping", "PutMapping", 
            "DeleteMapping", "PatchMapping", "Path"
        }

        method_query = """
            (method_declaration) @method_node
        """
        
        annotation_query = """
        [
            (annotation
                name: (identifier) @method_annotation
                arguments: (annotation_argument_list)? @annotation_args
            )
            (marker_annotation
                name: (identifier) @method_annotation
            )
        ] @annotation_node
        """

        endpoints = []
        method_captures = execute_query(class_body, method_query, self.language_name)

        for method_node_tuple in method_captures:
            method_node = method_node_tuple[0]
            
            modifiers_node = next((c for c in method_node.children if c.type == 'modifiers'), None)
            handler_name_node = method_node.child_by_field_name("name")
            params_node = method_node.child_by_field_name("parameters")
            
            if not modifiers_node or not handler_name_node:
                continue

            handler_name = self._get_text(handler_name_node)
            annot_captures = execute_query(modifiers_node, annotation_query, self.language_name)
            
            annot_nodes = {}
            for node, name in annot_captures:
                annot_node = node
                while annot_node and annot_node.type not in ['annotation', 'marker_annotation']:
                    annot_node = annot_node.parent
                if annot_node:
                    annot_nodes.setdefault(annot_node.start_byte, {})[name] = node

            annot_list = []
            method_type = "ANY"
            has_endpoint_annotation = False

            for data in annot_nodes.values():
                if "method_annotation" in data:
                    annot_name = self._get_text(data["method_annotation"])
                    args_node = data.get("annotation_args")
                    annot_list.append((annot_name, args_node))
                    
                    if annot_name in path_annotations:
                        has_endpoint_annotation = True
                    
                    if annot_name in method_mappings:
                        has_endpoint_annotation = True
                        new_method = method_mappings[annot_name]
                        if new_method != "ANY":
                            method_type = new_method
                        elif method_type == "ANY":
                            method_type = "ANY"

            if not has_endpoint_annotation:
                continue 

            paths = []
            for annot_name, args_node in annot_list:
                if annot_name in path_annotations:
                    literals = self._collect_string_literals(args_node)
                    if literals:
                        paths.extend(literals)
                    if annot_name == "Path" and method_type != "ANY":
                        break
            
            if not paths:
                paths = [""]

            method_auth = self._find_auth_annotations(modifiers_node)
            all_auth = list(set(class_auth + method_auth))
            
            for path in paths:
                full_path = f"{base_path}/{path}".replace("//", "/").rstrip('/')
                parameters = self._parse_java_parameters(params_node, method_node)
                
                endpoints.append(APIEndpoint(
                    file_path="", 
                    handler_name=handler_name,
                    http_method=method_type,
                    path=full_path or "/",
                    line_number=method_node.start_point[0] + 1,
                    snippet=self._get_text(method_node),
                    parameters=parameters,
                    auth_mechanisms=all_auth
                ))
                
        return endpoints

    def _parse_java_parameters(self, params_node: Node, method_node: Node) -> List[APIParameter]:
        """
        Parses method parameters to identify API parameters.

        Identifies parameters based on annotations like @PathVariable,
        @RequestParam, @RequestHeader, @CookieValue, etc.

        Args:
            params_node: The Node for the method's formal_parameters.
            method_node: The Node for the entire method declaration (for
                         parsing other annotations like @Parameter).

        Returns:
            A list of APIParameter objects.
        """
        parameters = []
        if not params_node:
            return parameters
            
        query = """
            (formal_parameter
                (modifiers 
                    (
                        [
                            (annotation
                                name: (identifier) @param_annotation
                            )
                            (marker_annotation
                                name: (identifier) @param_annotation
                            )
                        ]
                    )
                )?
                type: (type_identifier) @param_type
                name: (identifier) @param_name
            )
        """
        
        captures = execute_query(params_node, query, self.language_name)
        param_nodes = {}
        for node, name in captures:
            param_node = node
            while param_node and param_node.type != 'formal_parameter':
                param_node = param_node.parent
            if param_node:
                param_nodes.setdefault(param_node.start_byte, {})[name] = node

        for data in param_nodes.values():
            if "param_name" not in data or "param_type" not in data:
                continue

            annotation = self._get_text(data["param_annotation"]) if "param_annotation" in data else ""
            param_type = ParamType.BODY
            
            if annotation in ["PathVariable", "PathParam"]:
                param_type = ParamType.PATH
            elif annotation in ["RequestParam", "QueryParam"]:
                param_type = ParamType.QUERY
            elif annotation in ["RequestHeader", "HeaderParam"]:
                param_type = ParamType.HEADER
            elif annotation in ["CookieValue", "CookieParam"]:
                param_type = ParamType.COOKIE

            parameters.append(APIParameter(
                name=self._get_text(data["param_name"]),
                data_type=self._get_text(data["param_type"]),
                param_type=param_type,
                required=True 
            ))

        swagger_query = """
        [
            (annotation
                name: (identifier) @anno_name
            )
            (marker_annotation
                name: (identifier) @anno_name
            )
        ]
        """
        method_modifiers = next((c for c in method_node.children if c.type == 'modifiers'), None)
        if method_modifiers:
            captures = execute_query(method_modifiers, swagger_query, self.language_name)
            for node, name in captures:
                if name == "anno_name" and self._get_text(node) == "Parameter":
                    parameters.append(APIParameter(
                        name="swagger_param",
                        data_type="",
                        param_type=ParamType.QUERY,
                        required=False
                    ))
        return parameters

    def _find_class_auth(self, class_node: Node) -> List[str]:
        """
        Finds authentication annotations on a class node.

        Args:
            class_node: The tree-sitter Node for the class declaration.

        Returns:
            A list of auth-related annotation names.
        """
        modifiers = next((c for c in class_node.children if c.type == 'modifiers'), None)
        return self._find_auth_annotations(modifiers)

    def _find_auth_annotations(self, modifiers_node: Node) -> List[str]:
        """
        Helper function to find known auth annotations on a modifier node.

        Args:
            modifiers_node: The tree-sitter Node for modifiers.

        Returns:
            A list of unique auth-related annotation names found.
        """
        auths = []
        if not modifiers_node:
            return auths

        auth_names = {"PreAuthorize", "RolesAllowed", "Secured",
                      "PermitAll", "DenyAll",
                      "SecurityRequirement", "SecurityRequirements",
                      "PermissionRequired"}
        
        annotation_query = """
        [
            (annotation
                name: (identifier) @auth_name
            )
            (marker_annotation
                name: (identifier) @auth_name
            )
        ]
        """
        
        captures = execute_query(modifiers_node, annotation_query, self.language_name)
        for node, name in captures:
            if name == "auth_name":
                annot_name = self._get_text(node)
                if annot_name in auth_names:
                    auths.append(annot_name)
        return list(set(auths))