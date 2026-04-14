from lex2md.parser import parse_eurlex_html


def test_parse_empty_html() -> None:
    html = ""
    result = parse_eurlex_html(html)
    
    assert result["title"] == ""
    assert result["articles"] == []
    assert result["annexes"] == []
    assert result["preamble"] == ""


def test_parse_no_articles_but_preamble() -> None:
    html = """
    <html><body>
        <div id="pbl_1"><p>Just a preamble.</p></div>
    </body></html>
    """
    result = parse_eurlex_html(html)
    
    assert "Just a preamble" in result["preamble"]
    assert result["articles"] == []


def test_parse_broken_footnotes() -> None:
    # Footnote marker without corresponding text
    html = """
    <html><body>
        <div id="pbl_1">
           <p>Text<span class="oj-super oj-note-tag"><a id="ntc1-1" href="#ntr1">(1)</a></span>.</p>
        </div>
        <!-- missing the actual note for #ntr1 -->
    </body></html>
    """
    result = parse_eurlex_html(html)
    
    assert "(1)" in result["preamble"]
    assert "[^1]" not in result["preamble"]
    assert len(result["preamble_notes"]) == 0


def test_parse_missing_table_cells() -> None:
    html = """
    <html><body>
        <div class="eli-subdivision" id="art_1">
            <p class="ti-art">Article 1</p>
            <div class="eli-title">Title</div>
            <table>
                <tr><th>Col 1</th></tr>
                <tr><td>Val 1</td><td>Val 2 (extra)</td></tr>
            </table>
        </div>
    </body></html>
    """
    result = parse_eurlex_html(html)
    body = result["articles"][0]["body"]
    
    assert "| Col 1 |" in body
    assert "| Val 1 | Val 2 (extra) |" in body
