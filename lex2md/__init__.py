"""Core package for fetching and converting EUR-Lex documents to Markdown."""

from .fetcher import (
    DocumentNotFoundError,
    EurLexFetcherError,
    NetworkError,
    fetch_document_html,
)
from .markdown import generate_markdown
from .models import EurLexDocument, Note, Recital, Section, document_to_dict
from .parser import parse_document_html, parse_eurlex_html

__all__ = [
    "DocumentNotFoundError",
    "EurLexDocument",
    "EurLexFetcherError",
    "NetworkError",
    "Note",
    "Recital",
    "Section",
    "document_to_dict",
    "fetch_document_html",
    "generate_markdown",
    "parse_document_html",
    "parse_eurlex_html",
]
