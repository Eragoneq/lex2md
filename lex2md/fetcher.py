from __future__ import annotations

import requests


class EurLexFetcherError(Exception):
    """Base exception for EUR-Lex fetch failures."""


class DocumentNotFoundError(EurLexFetcherError):
    """Raised when a CELEX document cannot be found."""


class NetworkError(EurLexFetcherError):
    """Raised when the request fails for transport or HTTP reasons."""


def fetch_document_html(celex_id: str, language: str = "en") -> str:
    """Fetch EUR-Lex HTML/XHTML by CELEX identifier."""
    url = f"https://publications.europa.eu/resource/celex/{celex_id}"
    headers = {
        "Accept": "application/xhtml+xml,text/html",
        "Accept-Language": language,
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 404:
            raise DocumentNotFoundError(f"Document with CELEX ID {celex_id} not found.")
        response.raise_for_status()

        if _looks_like_waf_challenge(response.text):
            raise NetworkError(
                "EUR-Lex returned an anti-bot challenge page instead of legal text. "
                "Please retry later or use a browser-fetched local HTML file."
            )

        return response.text
    except requests.exceptions.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            raise DocumentNotFoundError(
                f"Document with CELEX ID {celex_id} not found."
            ) from exc
        raise NetworkError(f"HTTP error occurred: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise NetworkError(f"Network error occurred: {exc}") from exc


def _looks_like_waf_challenge(html: str) -> bool:
    lowered = html.lower()
    return (
        "awswafintegration" in lowered
        or "challenge.js" in lowered
        or "window.gokuprops" in lowered
        or "verify that you're not a robot" in lowered
    )
