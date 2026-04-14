from lex2md.parser import parse_document_html, parse_eurlex_html


def test_parse_eurlex_html_basic() -> None:
    html = """
    <html>
        <body>
            <h1 class="ti-main">REGULATION (EU) 2024/1183</h1>
            <div id="pbl_1">
                <p>THE EUROPEAN PARLIAMENT AND THE COUNCIL OF THE EUROPEAN UNION
                <span class="oj-super oj-note-tag"><a id="ntc1-1" href="#ntr1">(1)</a></span>,</p>
            </div>
            <div class="eli-subdivision" id="art_1">
                <p class="ti-art">Article 1</p>
                <div class="eli-title">Subject matter</div>
                <p>This ‘Regulation’ establishes a framework
                <span class="oj-super oj-note-tag"><a id="ntc2-1" href="#ntr2">(2)</a></span>.</p>
            </div>
            <p><a id="ntr1"></a>(1) OJ C 31, 27.1.2023, p. 1.</p>
            <p><a id="ntr2"></a>(2) Some other note.</p>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)

    assert result["title"] == "REGULATION (EU) 2024/1183"
    assert "THE EUROPEAN PARLIAMENT" in result["preamble"]
    assert "`Regulation`" in result["articles"][0]["body"]
    assert "[^1]" in result["preamble"]
    assert "[^2]" in result["articles"][0]["body"]
    assert len(result["preamble_notes"]) == 1
    assert result["preamble_notes"][0]["id"] == "1"
    assert "OJ C 31" in result["preamble_notes"][0]["text"]
    assert len(result["articles"][0]["notes"]) == 1
    assert result["articles"][0]["notes"][0]["id"] == "2"


def test_parse_document_html_returns_model() -> None:
    html = """
    <html>
        <body>
            <p class="Titreobjet_cp">PROPOSAL FOR A DIRECTIVE</p>
            <p class="Institutionquiagit">THE EUROPEAN COMMISSION
            <span class="oj-super oj-note-tag"><a id="ntc1-1" href="#ntr1">(1)</a></span>,</p>
            <p>Acting in accordance with...</p>
            <p class="Formuledadoption">HAS ADOPTED THIS DIRECTIVE:</p>
            <p class="Titrearticle"><span>Article 1</span>Objective</p>
            <p>The objective is ‘defined’ here.</p>
            <p><a id="ntr1"></a>(1) Commission Note.</p>
        </body>
    </html>
    """

    document = parse_document_html(html, celex="X", language="en")

    assert document.title == "PROPOSAL FOR A DIRECTIVE"
    assert document.celex == "X"
    assert document.language == "en"
    assert len(document.articles) == 1
    assert document.articles[0].id == "Article 1"
    assert "`defined`" in document.articles[0].body


def test_table_rendering_and_tblnote_outside_table() -> None:
    html = """
    <html>
        <body>
            <h1 class="ti-main">TABLE TEST</h1>
            <div class="eli-subdivision" id="art_1">
                <p class="ti-art">Article 1</p>
                <div class="eli-title">Data</div>
                <table>
                    <tr><th>Col A</th><th>Col B</th></tr>
                    <tr><td>A1</td><td>B1</td></tr>
                    <tr><td>A2</td><td>B2</td></tr>
                </table>
                <p class="oj-tblnote">Note: this is a table note.</p>
            </div>
        </body>
    </html>
    """

    document = parse_document_html(html)
    body = document.articles[0].body

    assert "| Col A | Col B |" in body
    assert "| --- | --- |" in body
    assert "| A1 | B1 |" in body
    assert "| A2 | B2 |" in body
    assert "\n\nNote: this is a table note." in body


def test_parenthesized_numbers_are_not_converted_without_note_markers() -> None:
    html = """
    <html>
        <body>
            <h1 class="ti-main">RECITAL TEST</h1>
            <div id="pbl_1">
                <p>(1) This is recital text and should remain plain numbering.</p>
                <p>See Article 4(2) for legal reference formatting.</p>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)

    assert "(1) This is recital text" in result["preamble"]
    assert "Article 4(2)" in result["preamble"]
    assert "[^1]" not in result["preamble"]
    assert result["preamble_notes"] == []


def test_preamble_is_split_into_intro_and_recitals() -> None:
    html = """
    <html>
        <body>
            <h1 class="ti-main">PREAMBLE SPLIT TEST</h1>
            <div id="pbl_1">
                <p>THE EUROPEAN COMMISSION,</p>
                <p>Having regard to the Treaty on the Functioning of the European Union,</p>
                <p>Whereas:</p>
                <p>(1) First recital text.</p>
                <p>(2) Second recital text.</p>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)

    assert result["preamble_intro"] == (
        "THE EUROPEAN COMMISSION,\n\n"
        "Having regard to the Treaty on the Functioning of the European Union,\n\n"
        "Whereas:"
    )
    assert result["preamble_recitals"] == [
        {"number": "1", "text": "First recital text."},
        {"number": "2", "text": "Second recital text."},
    ]


def test_only_ntc_to_ntr_note_links_are_extracted() -> None:
    html = """
    <html>
        <body>
            <h1 class="ti-main">LINK FILTER TEST</h1>
            <div id="pbl_1">
                <p>
                    Valid note
                    <span class="oj-super oj-note-tag"><a id="ntc1-1" href="#ntr1">(1)</a></span>
                    and invalid target
                    <span class="oj-super oj-note-tag"><a id="ntc2-1" href="#art_1">(2)</a></span>
                    and invalid link-id
                    <span class="oj-super oj-note-tag"><a id="abc3-1" href="#ntr3">(3)</a></span>.
                </p>
            </div>
            <p><a id="ntr1"></a>(1) Valid footnote.</p>
            <p><a id="ntr3"></a>(3) Should not be extracted by id filter.</p>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)

    assert "[^1]" in result["preamble"]
    assert "[^2]" not in result["preamble"]
    assert "[^3]" not in result["preamble"]
    assert len(result["preamble_notes"]) == 1
    assert result["preamble_notes"][0]["id"] == "1"


def test_article_body_is_split_into_paragraphs_and_points() -> None:
    html = """
    <html>
        <body>
            <h1 class="ti-main">POINT STRUCTURE TEST</h1>
            <div class="eli-subdivision" id="art_1">
                <p class="ti-art">Article 1</p>
                <div class="eli-title">Structure</div>
                <p>1. National certification schemes shall include at least: (a) governance rules; (b) review procedures.</p>
                <p>2. Scheme owners shall document decisions.</p>
                <p>3. Monitoring shall include:</p>
                <ul>
                    <li>feedback from stakeholders</li>
                    <li>requests for clarification</li>
                </ul>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)
    paragraphs = result["articles"][0]["paragraphs"]

    assert len(paragraphs) == 3
    assert paragraphs[0]["number"] == "1"
    assert (
        paragraphs[0]["text"]
        == "National certification schemes shall include at least:"
    )
    assert [point["marker"] for point in paragraphs[0]["points"]] == ["(a)", "(b)"]
    assert [point["style"] for point in paragraphs[0]["points"]] == [
        "lower_alpha",
        "lower_alpha",
    ]
    assert paragraphs[1]["number"] == "2"
    assert paragraphs[1]["points"] == []
    assert paragraphs[2]["number"] == "3"
    assert [point["marker"] for point in paragraphs[2]["points"]] == ["-", "-"]
    assert [point["text"] for point in paragraphs[2]["points"]] == [
        "feedback from stakeholders",
        "requests for clarification",
    ]


def test_table_cells_with_numbered_markers_are_exposed_as_points() -> None:
    html = """
    <html>
        <body>
            <h1 class="ti-main">TABLE POINT TEST</h1>
            <div class="eli-subdivision" id="art_2">
                <p class="ti-art">Article 2</p>
                <div class="eli-title">Definitions</div>
                <p>For the purpose of this Regulation, the following definitions apply:</p>
                <table>
                    <tr><td>(1)</td><td>`wallet solution` means a combination of software and hardware.</td></tr>
                </table>
                <table>
                    <tr><td>(2)</td><td>`scheme owner` means an organisation responsible for maintaining the scheme.</td></tr>
                </table>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)
    paragraphs = result["articles"][0]["paragraphs"]

    assert len(paragraphs) == 1
    assert paragraphs[0]["number"] == ""
    assert (
        paragraphs[0]["text"]
        == "For the purpose of this Regulation, the following definitions apply:"
    )
    assert [point["marker"] for point in paragraphs[0]["points"]] == ["(1)", "(2)"]
    assert [point["style"] for point in paragraphs[0]["points"]] == ["arabic", "arabic"]


def test_unnumbered_article_paragraphs_keep_empty_number() -> None:
    html = """
    <html>
        <body>
            <h1 class="ti-main">UNNUMBERED PARAGRAPH TEST</h1>
            <div class="eli-subdivision" id="art_3">
                <p class="ti-art">Article 3</p>
                <div class="eli-title">General provision</div>
                <p>This Article applies to all wallet providers.</p>
                <p>It also applies to their subcontractors.</p>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)
    paragraphs = result["articles"][0]["paragraphs"]

    assert len(paragraphs) == 2
    assert paragraphs[0]["number"] == ""
    assert paragraphs[0]["text"] == "This Article applies to all wallet providers."
    assert paragraphs[1]["number"] == ""
    assert paragraphs[1]["text"] == "It also applies to their subcontractors."


def test_point_detection_accepts_markers_after_full_stop() -> None:
    html = """
    <html>
        <body>
            <h1 class="ti-main">FULL STOP MARKER TEST</h1>
            <div class="eli-subdivision" id="art_8">
                <p class="ti-art">Article 8</p>
                <div class="eli-title">List continuity</div>
                <p>1. Requirements include: (a) first element. (b) second element.</p>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)
    points = result["articles"][0]["paragraphs"][0]["points"]

    assert [point["marker"] for point in points] == ["(a)", "(b)"]
    assert points[0]["text"] == "first element."
    assert points[1]["text"] == "second element."


def test_inline_points_support_last_item_ending_with_full_stop() -> None:
    html = """
    <html>
        <body>
            <h1 class="ti-main">LAST POINT TERMINATOR TEST</h1>
            <div class="eli-subdivision" id="art_9">
                <p class="ti-art">Article 9</p>
                <div class="eli-title">Terminators</div>
                <p>1. The framework shall include: (a) governance rules; (b) incident handling; and (c) periodic review.</p>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)
    paragraph = result["articles"][0]["paragraphs"][0]

    assert paragraph["number"] == "1"
    assert paragraph["text"] == "The framework shall include:"
    assert [point["marker"] for point in paragraph["points"]] == ["(a)", "(b)", "(c)"]
    assert paragraph["points"][2]["text"] == "periodic review."


def test_inline_points_extract_nested_subpoints() -> None:
    html = """
    <html>
        <body>
            <h1 class="ti-main">NESTED SUBPOINTS TEST</h1>
            <div class="eli-subdivision" id="art_10">
                <p class="ti-art">Article 10</p>
                <div class="eli-title">Nested points</div>
                <p>1. Information shall include: (a) basic details; (b) the applicable supervisory regime and information on the liability regime with respect to the following: (i) the party issuing the electronic identification means; and (ii) the party operating the authentication procedure.</p>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)
    paragraph = result["articles"][0]["paragraphs"][0]
    second_point = paragraph["points"][1]

    assert [point["marker"] for point in paragraph["points"]] == ["(a)", "(b)"]
    assert second_point["marker"] == "(b)"
    assert second_point["text"].endswith("the following:")
    assert [point["marker"] for point in second_point["subpoints"]] == ["(i)", "(ii)"]
    assert (
        second_point["subpoints"][0]["text"]
        == "the party issuing the electronic identification means; and"
    )
    assert (
        second_point["subpoints"][1]["text"]
        == "the party operating the authentication procedure."
    )


def test_extracts_chapter_metadata_and_final_signature() -> None:
    html = """
    <html>
        <body>
            <div id="cpt_I">
                <p class="oj-ti-section-1">CHAPTER I</p>
                <div class="eli-title">GENERAL PROVISIONS</div>
                <div class="eli-subdivision" id="art_1">
                    <p class="ti-art">Article 1</p>
                    <div class="eli-title">Subject matter</div>
                    <p>1. This Regulation applies.</p>
                </div>
            </div>
            <div id="fnp_1" class="eli-subdivision">
                <div class="oj-final">
                    <p class="oj-normal">This Regulation shall be binding in its entirety.</p>
                    <p class="oj-normal">Done at Brussels, 1 January 2026.</p>
                    <div class="oj-signatory">
                        <p class="oj-signatory">For the Commission</p>
                        <p class="oj-signatory">The President</p>
                        <p class="oj-signatory">Jane DOE</p>
                    </div>
                </div>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)

    assert result["articles"][0]["chapter_id"] == "CHAPTER I"
    assert result["articles"][0]["chapter_title"] == "GENERAL PROVISIONS"
    assert result["final_text"] == (
        "This Regulation shall be binding in its entirety.\n\n"
        "Done at Brussels, 1 January 2026."
    )
    assert result["signature_lines"] == [
        "For the Commission",
        "The President",
        "Jane DOE",
    ]


def test_extracts_nested_chapter_and_section_hierarchy() -> None:
    html = """
    <html>
        <body>
            <div id="cpt_III">
                <p class="oj-ti-section-1">CHAPTER III</p>
                <div class="eli-title" id="cpt_III.tit_1">
                    <p class="oj-ti-section-2">TRUST SERVICES</p>
                </div>
                <div id="cpt_III.sct_1">
                    <p class="oj-ti-section-1">SECTION 1</p>
                    <div class="eli-title" id="cpt_III.sct_1.tit_1">
                        <p class="oj-ti-section-2">General provisions</p>
                    </div>
                    <div class="eli-subdivision" id="art_1">
                        <p class="ti-art">Article 1</p>
                        <div class="eli-title">Scope</div>
                        <p>1. This applies.</p>
                    </div>
                </div>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)
    article = result["articles"][0]

    assert article["chapter_id"] == "CHAPTER III"
    assert article["chapter_title"] == "TRUST SERVICES"
    assert article["section_id"] == "SECTION 1"
    assert article["section_title"] == "General provisions"


def test_annex_uses_doc_title_and_renders_annex_sections() -> None:
    html = """
    <html>
        <body>
            <div class="eli-container" id="anx_I">
                <p class="oj-doc-ti">ANNEX I</p>
                <p class="oj-doc-ti">RISK REGISTER</p>
                <p class="oj-ti-grseq-1">SECTION I</p>
                <p class="oj-ti-grseq-1">General items</p>
                <p class="oj-normal">This is section text.</p>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)

    assert len(result["annexes"]) == 1
    assert result["annexes"][0]["id"] == "ANNEX I"
    assert result["annexes"][0]["title"] == "RISK REGISTER"
    assert "#### SECTION I - General items" in result["annexes"][0]["body"]
    assert result["annexes"][0]["paragraphs"][0]["number"] == ""


def test_complex_table_is_rendered_with_flattened_fallback() -> None:
    html = """
    <html>
        <body>
            <div class="eli-subdivision" id="art_1">
                <p class="ti-art">Article 1</p>
                <div class="eli-title">Table test</div>
                <table>
                    <tr>
                        <th>Type</th>
                        <th colspan="2">Description</th>
                    </tr>
                    <tr>
                        <td rowspan="2">A</td>
                        <td>One</td>
                        <td>Two</td>
                    </tr>
                    <tr>
                        <td>Three</td>
                        <td>Four</td>
                    </tr>
                </table>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)
    body = result["articles"][0]["body"]

    assert "<table>" in body
    assert '<th colspan="2"' in body
    assert '<td rowspan="2"' in body
    assert "A</td>" in body
    assert "style=" not in body


def test_table_with_point_markers_is_converted_to_plain_point_lines() -> None:
    html = """
    <html>
        <body>
            <div class="eli-container" id="anx_I">
                <p class="oj-doc-ti">ANNEX I</p>
                <p class="oj-doc-ti">Requirements</p>
                <table>
                    <tr><th>Point</th><th>Description</th></tr>
                    <tr><td>(a)</td><td>First requirement.</td></tr>
                    <tr><td>(b)</td><td>Second requirement.</td></tr>
                </table>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)
    body = result["annexes"][0]["body"]

    assert "(a) First requirement." in body
    assert "(b) Second requirement." in body
    assert "| Point | Description |" not in body


def test_annex_footnotes_are_namespaced_to_avoid_conflicts() -> None:
    html = """
    <html>
        <body>
            <div class="eli-subdivision" id="art_1">
                <p class="ti-art">Article 1</p>
                <div class="eli-title">Body</div>
                <p>Article text<span class="oj-super oj-note-tag"><a id="ntc1-a" href="#ntr1-a">(1)</a></span>.</p>
            </div>
            <div class="eli-container" id="anx_I">
                <p class="oj-doc-ti">ANNEX I</p>
                <p class="oj-doc-ti">Annex title</p>
                <p>Annex text<span class="oj-super oj-note-tag"><a id="ntc1-b" href="#ntr1-b">(1)</a></span>.</p>
            </div>
            <p><a id="ntr1-a"></a>(1) Article note text.</p>
            <p><a id="ntr1-b"></a>(1) Annex note text.</p>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)

    assert "[^1]" in result["articles"][0]["body"]
    assert "[^annex-i-1]" in result["annexes"][0]["body"]
    assert result["articles"][0]["notes"][0]["id"] == "1"
    assert result["annexes"][0]["notes"][0]["id"] == "annex-i-1"
    assert "Annex note text." not in result["annexes"][0]["body"]


def test_parenthesized_paragraphs_are_split_in_annex_style_blocks() -> None:
    html = """
    <html>
        <body>
            <div class="eli-container" id="anx_IV">
                <p class="oj-doc-ti">ANNEX IV</p>
                <p class="oj-doc-ti">Evaluation activities</p>
                <p>(1) First paragraph text.</p>
                <p>(2) Second paragraph text with list: (a) alpha item; (b) beta item.</p>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)
    paragraphs = result["annexes"][0]["paragraphs"]

    assert len(paragraphs) == 2
    assert paragraphs[0]["number"] == "1"
    assert paragraphs[1]["number"] == "2"
    assert [point["marker"] for point in paragraphs[1]["points"]] == ["(a)", "(b)"]


def test_point_like_table_deduplicates_cells_after_multispan_normalization() -> None:
    html = """
    <html>
        <body>
            <div class="eli-container" id="anx_V">
                <p class="oj-doc-ti">ANNEX V</p>
                <p class="oj-doc-ti">List</p>
                <table>
                    <tr><td>(a)</td><td colspan="2">Duplicated text</td></tr>
                </table>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)
    body = result["annexes"][0]["body"]

    assert "<table>" in body
    assert 'colspan="2"' in body
    assert "Duplicated text" in body


def test_simple_markdown_table_uses_double_dash_separator() -> None:
    html = """
    <html>
        <body>
            <div class="eli-subdivision" id="art_1">
                <p class="ti-art">Article 1</p>
                <div class="eli-title">Simple table</div>
                <table>
                    <tr><th>A</th><th>B</th></tr>
                    <tr><td>1</td><td>2</td></tr>
                </table>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)
    body = result["articles"][0]["body"]

    assert "| A | B |" in body
    assert "| --- | --- |" in body


def test_complex_table_skips_redundant_split_rows() -> None:
    html = """
    <html>
        <body>
            <div class="eli-container" id="anx_I">
                <p class="oj-doc-ti">ANNEX I</p>
                <p class="oj-doc-ti">Complex table</p>
                <table>
                    <tr><th>A</th><th>B</th><th>C</th></tr>
                    <tr><td rowspan="2">TT5</td><td rowspan="2">Malicious actions</td><td>5.1 Interception of information</td></tr>
                    <tr><td>5.1</td><td>Interception of information</td></tr>
                </table>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)
    body = result["annexes"][0]["body"]

    assert "<td>5.1 Interception of information</td>" in body
    assert "<td>5.1</td>" not in body
    assert "<td>Interception of information</td>" not in body


def test_complex_table_skips_redundant_split_rows_without_rowspan() -> None:
    html = """
    <html>
        <body>
            <div class="eli-container" id="anx_I">
                <p class="oj-doc-ti">ANNEX I</p>
                <p class="oj-doc-ti">Complex table</p>
                <table>
                    <tr><th>A</th><th>B</th><th>C</th></tr>
                    <tr><td rowspan="3">TT4</td><td rowspan="3">Failure and outages</td><td>4.1 Failure or dysfunction of equipment</td></tr>
                    <tr><td>4.1</td><td>Failure or dysfunction of equipment</td></tr>
                    <tr><td>4.2 Loss of resources</td></tr>
                    <tr><td>4.2</td><td>Loss of resources</td></tr>
                </table>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)
    body = result["annexes"][0]["body"]

    assert "<td>4.2 Loss of resources</td>" in body
    assert "<td>4.2</td>" not in body
    assert "<td>Loss of resources</td>" not in body


def test_complex_table_skips_redundant_split_rows_with_three_cell_previous_row() -> (
    None
):
    html = """
    <html>
        <body>
            <div class="eli-container" id="anx_I">
                <p class="oj-doc-ti">ANNEX I</p>
                <p class="oj-doc-ti">Complex table</p>
                <table>
                    <tr><th>A</th><th>B</th><th>C</th></tr>
                    <tr><td rowspan="2">TT2</td><td rowspan="2">Errors</td><td>2.1 Something</td></tr>
                    <tr><td>2.2 Something else</td></tr>
                    <tr><td>TT3</td><td>Use of unreliable resources</td><td>3.1 Erroneous use or configuration of wallet components</td></tr>
                    <tr><td>3.1</td><td>Erroneous use or configuration of wallet components</td></tr>
                </table>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)
    body = result["annexes"][0]["body"]

    assert "<td>TT3</td>" in body
    assert "<td>Use of unreliable resources</td>" in body
    assert "<td>3.1 Erroneous use or configuration of wallet components</td>" in body
    assert "<td>3.1</td>" not in body
    assert "<td>Erroneous use or configuration of wallet components</td>" not in body


def test_duplicate_point_lines_are_collapsed_in_paragraph_points() -> None:
    html = """
    <html>
        <body>
            <div class="eli-container" id="anx_IV">
                <p class="oj-doc-ti">ANNEX IV</p>
                <p class="oj-doc-ti">Methods</p>
                <p>(1) Main clause.</p>
                <p>(a) repeated item;</p>
                <p>(b) unique item.</p>
                <p>(a) repeated item;</p>
            </div>
        </body>
    </html>
    """

    result = parse_eurlex_html(html)
    points = result["annexes"][0]["paragraphs"][0]["points"]

    assert [point["marker"] for point in points] == ["(a)", "(b)"]
