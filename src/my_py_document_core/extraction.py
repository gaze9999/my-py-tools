"""Stable extraction API backed by the existing document CLI implementation."""

from .documents.convert_to_markdown import (
    GeneratedMarkdown,
    SUPPORTED_EXTENSIONS,
    _fenced_text as fenced_text,
    build_markdown,
    sha256,
)

__all__ = ["GeneratedMarkdown", "SUPPORTED_EXTENSIONS", "fenced_text", "build_markdown", "sha256"]
