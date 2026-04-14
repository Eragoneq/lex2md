from unittest.mock import Mock, patch

import pytest
import requests

from lex2md.fetcher import DocumentNotFoundError, NetworkError, fetch_document_html


def test_fetch_document_html_success() -> None:
    celex_id = "32024R1183"
    expected_html = "<html><body>Some content</body></html>"

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = expected_html
    mock_response.raise_for_status = Mock()

    with patch("requests.get", return_value=mock_response) as mock_get:
        result = fetch_document_html(celex_id)

    assert result == expected_html
    mock_get.assert_called_once()
    args, kwargs = mock_get.call_args
    assert celex_id in args[0]
    assert kwargs["headers"]["Accept-Language"] == "en"


def test_fetch_document_html_not_found() -> None:
    celex_id = "INVALID_CELEX"

    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.raise_for_status = Mock()

    with patch("requests.get", return_value=mock_response):
        with pytest.raises(DocumentNotFoundError):
            fetch_document_html(celex_id)


def test_fetch_document_html_http_error() -> None:
    celex_id = "32024R1183"

    mock_response = Mock()
    mock_response.status_code = 500
    http_error = requests.exceptions.HTTPError(
        "Internal Server Error", response=mock_response
    )
    mock_response.raise_for_status.side_effect = http_error

    with patch("requests.get", return_value=mock_response):
        with pytest.raises(NetworkError):
            fetch_document_html(celex_id)


def test_fetch_document_html_request_exception() -> None:
    celex_id = "32024R1183"

    with patch(
        "requests.get",
        side_effect=requests.exceptions.ConnectionError("Connection failed"),
    ):
        with pytest.raises(NetworkError):
            fetch_document_html(celex_id)


def test_fetch_document_html_detects_waf_challenge_page() -> None:
    celex_id = "32024R1183"
    challenge_html = """
    <html>
      <head><script>window.gokuProps = {};</script><script src="challenge.js"></script></head>
      <body>verify that you're not a robot</body>
    </html>
    """

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = challenge_html
    mock_response.raise_for_status = Mock()

    with patch("requests.get", return_value=mock_response):
        with pytest.raises(NetworkError):
            fetch_document_html(celex_id)
