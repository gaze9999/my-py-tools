"""Versioned document APIs for MCP servers and other local Python applications."""

API_VERSION = 1

from . import extraction, matching, updates, validation

__all__ = ["API_VERSION", "extraction", "matching", "updates", "validation"]
