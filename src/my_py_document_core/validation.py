"""Stable bounded Markdown validation API backed by the existing CLI source."""

from .markdown.validate_structure import analyze

__all__ = ["analyze"]
