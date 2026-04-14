from unittest.mock import MagicMock, mock_open

import pytest

from lex2md.cli import main
from lex2md.fetcher import EurLexFetcherError


@pytest.fixture
def mock_fetch(mocker):
    return mocker.patch("lex2md.cli.fetch_document_html", return_value="<html></html>")


@pytest.fixture
def mock_parse(mocker):
    mock_doc = MagicMock()
    return mocker.patch("lex2md.cli.parse_document_html", return_value=mock_doc)


@pytest.fixture
def mock_markdown(mocker):
    return mocker.patch("lex2md.cli.generate_markdown", return_value="# Markdown")


@pytest.fixture
def mock_dict(mocker):
    return mocker.patch("lex2md.cli.document_to_dict", return_value={"title": "Test"})


def test_cli_outputs_markdown(mocker, mock_fetch, mock_parse, mock_markdown):
    mocker.patch("sys.argv", ["lex2md", "12345"])
    m_open = mocker.patch("builtins.open", mock_open())

    main()

    mock_fetch.assert_called_once_with("12345", "en")
    m_open.assert_called_once_with("12345.md", "w", encoding="utf-8")
    m_open().write.assert_called_once_with("# Markdown")


def test_cli_custom_output(mocker, mock_fetch, mock_parse, mock_markdown):
    mocker.patch("sys.argv", ["lex2md", "12345", "-o", "custom.md", "-l", "fr"])
    m_open = mocker.patch("builtins.open", mock_open())

    main()

    mock_fetch.assert_called_once_with("12345", "fr")
    m_open.assert_called_once_with("custom.md", "w", encoding="utf-8")


def test_cli_json_mode(mocker, mock_fetch, mock_parse, mock_dict, capsys):
    mocker.patch("sys.argv", ["lex2md", "12345", "--json"])

    main()

    captured = capsys.readouterr()
    assert '"title": "Test"' in captured.out
    assert "Fetching document 12345" not in captured.err


def test_cli_local_mode(mocker, mock_fetch, mock_parse, mock_markdown):
    mocker.patch("sys.argv", ["lex2md", "12345", "--local", "dummy.html"])
    m_open = mocker.patch("builtins.open", mock_open(read_data="<html></html>"))

    main()

    mock_fetch.assert_not_called()
    m_open.assert_any_call("dummy.html", encoding="utf-8")


def test_cli_handles_fetch_error(mocker, mock_fetch):
    mocker.patch("sys.argv", ["lex2md", "12345"])
    mock_fetch.side_effect = EurLexFetcherError("Network error")

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1


def test_cli_handles_unexpected_error(mocker, mock_fetch):
    mocker.patch("sys.argv", ["lex2md", "12345"])
    mock_fetch.side_effect = ValueError("Something went wrong")

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
