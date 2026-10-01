"""Stable guarded Markdown API backed by the existing Markdown CLI."""

from .markdown.guarded_markdown_update import (
    headings,
    prepare,
    read_target,
    section,
    sha,
    write_guarded,
)

__all__ = ["headings", "prepare", "read_target", "section", "sha", "write_guarded"]
