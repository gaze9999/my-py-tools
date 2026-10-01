"""Versioned deterministic APIs for local workspace inspection."""

API_VERSION = 1

from . import environment, validation

__all__ = ["API_VERSION", "environment", "validation"]
