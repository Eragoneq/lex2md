import os
from pathlib import Path

from lex2md.parser import parse_document_html

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_integration_can_parse_real_documents():
    # Only run integration test if fixtures are present
    if not FIXTURE_DIR.exists():
        return

    for html_file in FIXTURE_DIR.glob("*.html"):
        with open(html_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        celex = html_file.stem
        # It shouldn't crash, and it should at least find the title
        document = parse_document_html(content, celex=celex, language="en")
        
        assert document.title != ""
        assert document.celex == celex
        assert document.language == "en"
        assert len(document.articles) > 0
