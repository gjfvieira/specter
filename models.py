from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class ParamType(str, Enum):
    """
    Enumeration defining the possible types of API parameters.
    
    Attributes:
        PATH: URL path parameter (e.g., /users/{id})
        QUERY: URL query parameter (e.g., ?page=1)
        BODY: Request body parameter
        HEADER: HTTP header parameter
        COOKIE: Cookie parameter
    """
    PATH = "path"
    QUERY = "query"
    BODY = "body"  
    HEADER = "header"
    COOKIE = "cookie"

class APIParameter(BaseModel):
    """
    Model representing a single parameter in an API endpoint.
    
    Attributes:
        name: Parameter identifier/name
        param_type: Type of parameter (path, query, body, etc.)
        data_type: Expected data type of the parameter value
        required: Whether the parameter is mandatory
        
    Examples:
        >>> param = APIParameter(
        ...     name="user_id",
        ...     param_type=ParamType.PATH,
        ...     data_type="integer",
        ...     required=True
        ... )
    """
    name: str = Field(..., description="The name of the parameter.")
    param_type: ParamType = Field(..., description="The type of the parameter (path, query, etc.).")
    data_type: str = Field(..., description="The data type of the parameter (e.g., 'int', 'string', 'UserDTO').")
    required: bool = Field(False, description="Whether the parameter is required.")

class APIEndpoint(BaseModel):
    """
    Model representing a discovered API endpoint from source code analysis.
    
    This model contains all relevant information about an API endpoint,
    including its location in source code, HTTP method, path, parameters,
    and security requirements.
    
    Attributes:
        file_path: Relative path to the source file containing the endpoint
        handler_name: Function/method name handling the endpoint
        http_method: HTTP verb (GET, POST, etc.)
        path: URL path pattern
        line_number: Source code line number where endpoint is defined
        snippet: Related source code excerpt
        parameters: List of endpoint parameters
        auth_mechanisms: List of security mechanisms required
        
    Examples:
        >>> endpoint = APIEndpoint(
        ...     file_path="api/users.py",
        ...     handler_name="get_user",
        ...     http_method="GET",
        ...     path="/users/{id}",
        ...     line_number=42,
        ...     snippet="@app.get('/users/{id}')\ndef get_user(id: int):",
        ...     parameters=[APIParameter(...)],
        ...     auth_mechanisms=["jwt"]
        ... )
    """
    file_path: str = Field(..., description="The relative path to the source file containing the endpoint definition.")
    handler_name: str = Field(..., description="The name of the function or method handling the endpoint.")
    http_method: str = Field(..., description="The HTTP method (e.g., 'GET', 'POST').")
    path: str = Field(..., description="The URL path of the endpoint.")
    line_number: int = Field(..., description="The line number where the endpoint is defined.")
    snippet: str = Field(..., description="The source code snippet for the endpoint definition.")
    parameters: List[APIParameter] = Field(default_factory=list, description="A list of parameters for the endpoint.")
    auth_mechanisms: List[str] = Field(default_factory=list, description="A list of identified authentication/authorization mechanisms.")