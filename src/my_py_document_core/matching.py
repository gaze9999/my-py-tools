"""Stable API for locating Markdown extracts generated from original sources."""

from .documents.locate_markdown_extracts import locate_extracts, metadata_records

__all__ = ["locate_extracts", "metadata_records"]
