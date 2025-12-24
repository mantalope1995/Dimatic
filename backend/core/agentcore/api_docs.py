"""
AgentCore API Documentation Helpers (Phase 10)

OpenAPI/Swagger documentation helpers for AgentCore API endpoints.

Phase 10: Enhanced API documentation with response schemas, examples,
and comprehensive descriptions for AgentCore operations in ap-southeast-2.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from functools import wraps

# Phase 10 default region
PHASE_10_REGION = "ap-southeast-2"

# ============================================================================
# Enums and Data Classes
# ============================================================================

class HTTPStatus(str, Enum):
    """HTTP status codes for API responses."""
    OK = "200"
    CREATED = "201"
    ACCEPTED = "202"
    NO_CONTENT = "204"
    BAD_REQUEST = "400"
    UNAUTHORIZED = "401"
    FORBIDDEN = "403"
    NOT_FOUND = "404"
    CONFLICT = "409"
    TOO_MANY_REQUESTS = "429"
    INTERNAL_SERVER_ERROR = "500"
    SERVICE_UNAVAILABLE = "503"


@dataclass
class APIResponse:
    """
    Standard API response structure.

    Attributes:
        success: Whether the request was successful
        message: Human-readable message
        data: Response payload (optional)
        error: Error details (if success=False)
        metadata: Response metadata
        region: AWS region (enforced ap-southeast-2)
        timestamp: Response timestamp
    """
    success: bool
    message: str
    data: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    region: str = PHASE_10_REGION
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "success": self.success,
            "message": self.message,
            "region": self.region,
            "timestamp": self.timestamp.isoformat(),
        }

        if self.data is not None:
            result["data"] = self.data

        if self.error:
            result["error"] = self.error

        if self.metadata:
            result["metadata"] = self.metadata

        return result


@dataclass
class ErrorDetail:
    """
    Detailed error information for API responses.

    Attributes:
        code: Error code (e.g., "RATE_LIMIT_EXCEEDED")
        message: Human-readable error message
        field: Field that caused the error (optional)
        details: Additional error details
        suggestion: Suggested fix (optional)
    """
    code: str
    message: str
    field: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "code": self.code,
            "message": self.message,
        }

        if self.field:
            result["field"] = self.field

        if self.details:
            result["details"] = self.details

        if self.suggestion:
            result["suggestion"] = self.suggestion

        return result


@dataclass
class PaginationInfo:
    """
    Pagination metadata for list responses.

    Attributes:
        page: Current page number (1-indexed)
        page_size: Number of items per page
        total_items: Total number of items
        total_pages: Total number of pages
        has_next: Whether there is a next page
        has_prev: Whether there is a previous page
    """
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "page": self.page,
            "page_size": self.page_size,
            "total_items": self.total_items,
            "total_pages": self.total_pages,
            "has_next": self.has_next,
            "has_prev": self.has_prev,
        }


@dataclass
class PaginatedResponse(APIResponse):
    """
    Paginated API response.

    Attributes:
        success: Whether the request was successful
        message: Human-readable message
        items: List of items for current page
        pagination: Pagination information
        region: AWS region
        timestamp: Response timestamp
    """
    items: List[Any] = field(default_factory=list)
    pagination: Optional[PaginationInfo] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = super().to_dict()
        result["items"] = self.items

        if self.pagination:
            result["pagination"] = self.pagination.to_dict()

        return result


# ============================================================================
# OpenAPI Documentation Helpers
# ============================================================================

class APIDocHelper:
    """
    Helper class for generating OpenAPI documentation.

    Provides decorators and utilities for enhancing FastAPI
    endpoint documentation with comprehensive examples,
    response schemas, and descriptions.
    """

    @staticmethod
    def success_response(
        description: str,
        example: Optional[Dict[str, Any]] = None,
        model: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Generate success response documentation.

        Args:
            description: Response description
            example: Example response data
            model: Pydantic model for response schema

        Returns:
            OpenAPI response specification
        """
        response = {
            "description": description,
            "content": {
                "application/json": {
                    "example": example or {
                        "success": True,
                        "message": description,
                        "region": PHASE_10_REGION,
                    }
                }
            }
        }

        if model:
            response["content"]["application/json"]["schema"] = {
                "$ref": f"#/components/schemas/{model.__name__}"
            }

        return response

    @staticmethod
    def error_response(
        description: str,
        error_code: str,
        example_message: str,
        suggestions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generate error response documentation.

        Args:
            description: Error description
            error_code: Error code
            example_message: Example error message
            suggestions: Optional list of suggestions

        Returns:
            OpenAPI error response specification
        """
        error_example = {
            "success": False,
            "message": example_message,
            "error": {
                "code": error_code,
                "message": example_message,
                "suggestion": suggestions[0] if suggestions else None,
            },
            "region": PHASE_10_REGION,
        }

        return {
            "description": description,
            "content": {
                "application/json": {
                    "example": error_example
                }
            }
        }

    @staticmethod
    def paginated_response(
        description: str,
        example_items: List[Any],
        total_items: int = 100,
        page: int = 1,
        page_size: int = 10
    ) -> Dict[str, Any]:
        """
        Generate paginated response documentation.

        Args:
            description: Response description
            example_items: Example items for the page
            total_items: Total number of items
            page: Current page number
            page_size: Number of items per page

        Returns:
            OpenAPI paginated response specification
        """
        total_pages = (total_items + page_size - 1) // page_size

        return {
            "description": description,
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": description,
                        "items": example_items[:page_size],
                        "pagination": {
                            "page": page,
                            "page_size": page_size,
                            "total_items": total_items,
                            "total_pages": total_pages,
                            "has_next": page < total_pages,
                            "has_prev": page > 1,
                        },
                        "region": PHASE_10_REGION,
                    }
                }
            }
        }


# ============================================================================
# Response Builders
# ============================================================================

class ResponseBuilder:
    """
    Builder for creating standardized API responses.

    Usage:
        ```python
        # Success response
        response = ResponseBuilder.success(
            message="Agent created",
            data={"agent_id": "agent-123"}
        )

        # Error response
        response = ResponseBuilder.error(
            message="Validation failed",
            error_code="VALIDATION_ERROR",
            field="agent_name"
        )

        # Paginated response
        response = ResponseBuilder.paginated(
            items=agents,
            page=1,
            page_size=10,
            total_items=100
        )
        ```
    """

    @staticmethod
    def success(
        message: str,
        data: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> APIResponse:
        """Create a success response."""
        return APIResponse(
            success=True,
            message=message,
            data=data,
            metadata=metadata or {},
        )

    @staticmethod
    def error(
        message: str,
        error_code: Optional[str] = None,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None,
    ) -> APIResponse:
        """Create an error response."""
        error_detail = ErrorDetail(
            code=error_code or "UNKNOWN_ERROR",
            message=message,
            field=field,
            details=details,
            suggestion=suggestion,
        )

        return APIResponse(
            success=False,
            message=message,
            error=error_detail.to_dict(),
        )

    @staticmethod
    def paginated(
        items: List[Any],
        page: int,
        page_size: int,
        total_items: Optional[int] = None,
        message: str = "Success"
    ) -> PaginatedResponse:
        """Create a paginated response."""
        total_items = total_items or len(items)
        total_pages = max(1, (total_items + page_size - 1) // page_size)

        pagination = PaginationInfo(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )

        return PaginatedResponse(
            success=True,
            message=message,
            items=items,
            pagination=pagination,
        )


# ============================================================================
# Decorators
# ============================================================================

def document_endpoint(
    summary: str,
    description: str,
    tags: List[str],
    responses: Optional[Dict[int, Dict[str, Any]]] = None,
):
    """
    Decorator for documenting FastAPI endpoints.

    Usage:
        ```python
        @app.get("/agents", tags=["AgentCore"])
        @document_endpoint(
            summary="List all agents",
            description="Retrieve a paginated list of all AgentCore agents...",
            tags=["AgentCore"],
            responses={
                200: APIDocHelper.paginated_response(...),
                401: APIDocHelper.error_response(...),
            }
        )
        async def list_agents(...):
            ...
        ```
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        # Add documentation attributes for FastAPI to pick up
        wrapper.summary = summary
        wrapper.description = description
        wrapper.tags = tags
        wrapper.responses = responses or {}

        return wrapper

    return decorator


# ============================================================================
# Example Generators
# ============================================================================

class ExampleGenerator:
    """
    Generate example data for API documentation.

    Provides realistic example data for different AgentCore
    resources and operations.
    """

    @staticmethod
    def agent_example() -> Dict[str, Any]:
        """Generate example agent data."""
        return {
            "agent_id": "agent-abc123",
            "name": "Research Assistant",
            "description": "AI agent for research tasks",
            "runtime_enabled": True,
            "memory_enabled": True,
            "code_interpreter_enabled": True,
            "browser_enabled": False,
            "status": "ACTIVE",
            "created_at": "2024-01-15T10:30:00Z",
            "region": PHASE_10_REGION,
        }

    @staticmethod
    def execution_example() -> Dict[str, Any]:
        """Generate example execution data."""
        return {
            "execution_id": "exec-xyz789",
            "agent_id": "agent-abc123",
            "status": "RUNNING",
            "started_at": "2024-01-15T10:35:00Z",
            "input_tokens": 150,
            "output_tokens": 300,
            "duration_seconds": 5.2,
            "region": PHASE_10_REGION,
        }

    @staticmethod
    def deployment_example() -> Dict[str, Any]:
        """Generate example deployment data."""
        return {
            "deployment_id": "deploy-def456",
            "agent_id": "agent-abc123",
            "status": "DEPLOYED",
            "endpoint": f"https://gateway.agentcore.{PHASE_10_REGION}.amazonaws.com/deploy-def456",
            "created_at": "2024-01-15T10:30:00Z",
            "region": PHASE_10_REGION,
        }

    @staticmethod
    def memory_resource_example() -> Dict[str, Any]:
        """Generate example memory resource data."""
        return {
            "memory_id": "memory-ghi789",
            "agent_id": "agent-abc123",
            "storage_type": "SEMANTIC",
            "status": "ACTIVE",
            "created_at": "2024-01-15T10:30:00Z",
            "region": PHASE_10_REGION,
        }


# ============================================================================
# FastAPI Integration Helpers
# ============================================================================

def get_openapi_schema(
    title: str,
    version: str,
    description: str,
    tags: List[Dict[str, str]]
) -> Dict[str, Any]:
    """
    Generate OpenAPI schema for FastAPI application.

    Args:
        title: API title
        version: API version
        description: API description
        tags: List of tag definitions

    Returns:
        OpenAPI schema dictionary
    """
    return {
        "openapi": "3.0.0",
        "info": {
            "title": title,
            "version": version,
            "description": description,
            "x-region": PHASE_10_REGION,
        },
        "tags": tags,
        "paths": {},
        "components": {
            "schemas": {
                "APIResponse": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                        "message": {"type": "string"},
                        "data": {"type": "object"},
                        "error": {"type": "object"},
                        "metadata": {"type": "object"},
                        "region": {"type": "string"},
                        "timestamp": {"type": "string", "format": "date-time"},
                    },
                },
                "ErrorDetail": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "field": {"type": "string"},
                        "details": {"type": "object"},
                        "suggestion": {"type": "string"},
                    },
                },
            },
        },
    }


# Predefined tags for AgentCore API documentation
AGENTCORE_TAGS = [
    {
        "name": "Runtime",
        "description": "AgentCore Runtime deployment and execution operations",
    },
    {
        "name": "Memory",
        "description": "Memory resource management for agent knowledge storage",
    },
    {
        "name": "Code Interpreter",
        "description": "Secure code execution in isolated sandboxes",
    },
    {
        "name": "Browser",
        "description": "Cloud-based browser automation",
    },
    {
        "name": "Gateway",
        "description": "MCP server integration and tool invocation",
    },
    {
        "name": "Billing",
        "description": "Usage tracking and billing integration",
    },
    {
        "name": "Health",
        "description": "Health check and monitoring endpoints",
    },
]


# Export public symbols
__all__ = [
    "PHASE_10_REGION",
    "HTTPStatus",
    "APIResponse",
    "ErrorDetail",
    "PaginationInfo",
    "PaginatedResponse",
    "APIDocHelper",
    "ResponseBuilder",
    "document_endpoint",
    "ExampleGenerator",
    "get_openapi_schema",
    "AGENTCORE_TAGS",
]
