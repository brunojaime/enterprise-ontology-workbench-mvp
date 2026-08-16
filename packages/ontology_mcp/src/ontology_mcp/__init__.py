"""MCP adapter for ontology services."""

from ontology_mcp.config import McpSettings
from ontology_mcp.server import create_server

__all__ = ["McpSettings", "create_server", "__version__"]

__version__ = "0.1.0"
