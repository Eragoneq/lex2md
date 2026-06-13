from lex2md.markdown import generate_markdown
from lex2md.models import EurLexDocument, Note, Paragraph, Point, Section


def test_generate_markdown_with_notes_and_navigation() -> None:
    document = EurLexDocument(
        title="REGULATION 123",
        preamble="See Article 1 and ANNEX I with [^1].",
        preamble_notes=[Note(id="1", text="Note 1 text")],
        articles=[
            Section(
                id="Article 1",
                title="Subject",
                chapter_id="CHAPTER I",
                chapter_title="GENERAL",
                body="Body of Article 1 with [^2].",
                notes=[Note(id="2", text="Note 2 text")],
            )
        ],
        annexes=[
            Section(
                id="ANNEX I", title="List", body="Item 1", notes=[]
            )
        ],
        celex="32024R0111",
        language="en",
    )

    result = generate_markdown(document)

    assert "# REGULATION 123" in result
    assert "- CELEX: `32024R0111`" in result
    # Navigation is only generated for wikilinks mode
    assert "## Navigation" not in result
    assert "### CHAPTER I - GENERAL" in result
    assert "See [Article 1](#Article%201%20-%20Subject) and [ANNEX I](#ANNEX%20I%20-%20List) with [^1]." in result
    assert "[^1]: Note 1 text" in result
    assert "[^2]: Note 2 text" in result


def test_generate_markdown_accepts_dict() -> None:
    parsed_data = {
        "title": "REGULATION 123",
        "preamble": "Some preamble text with [^1].",
        "preamble_notes": [{"id": "1", "text": "Note 1 text"}],
        "articles": [
            {
                "id": "Article 1",
                "title": "Subject",
                "chapter_id": "CHAPTER I",
                "chapter_title": "GENERAL",
                "body": "Body of Article 1 with [^2].",
                "notes": [{"id": "2", "text": "Note 2 text"}],
            }
        ],
        "annexes": [],
    }

    result = generate_markdown(parsed_data)

    assert "# REGULATION 123" in result
    assert "Some preamble text with [^1]." in result
    assert "### CHAPTER I - GENERAL" in result
    assert "[^1]: Note 1 text" in result
    assert "[Article 1](#Article%201%20-%20Subject)" in result
    assert "[^2]: Note 2 text" in result


def test_generate_markdown_renders_paragraph_points_as_sublists() -> None:
    document = EurLexDocument(
        title="REGULATION 456",
        articles=[
            Section(
                id="Article 3",
                title="Structure",
                body="",
                paragraphs=[
                    Paragraph(
                        number="1",
                        text="The scheme shall define:",
                        points=[
                            Point(
                                marker="(a)",
                                style="lower_alpha",
                                text="governance rules",
                            ),
                            Point(
                                marker="(b)",
                                style="lower_alpha",
                                text="review procedures",
                            ),
                        ],
                    ),
                    Paragraph(
                        number="2",
                        text="The scheme shall provide:",
                        points=[
                            Point(marker="(1)", style="arabic", text="risk assessment"),
                            Point(
                                marker="(2)", style="arabic", text="periodic updates"
                            ),
                        ],
                    ),
                ],
                notes=[],
            )
        ],
    )

    result = generate_markdown(document)

    assert "1. The scheme shall define:" in result
    assert "   - (a) governance rules" in result
    assert "   - (b) review procedures" in result
    assert "2. The scheme shall provide:" in result
    assert "   - (1) risk assessment" in result
    assert "   - (2) periodic updates" in result


def test_generate_markdown_renders_nested_subpoints_under_point() -> None:
    document = EurLexDocument(
        title="REGULATION 457",
        articles=[
            Section(
                id="Article 3",
                title="Structure",
                body="",
                paragraphs=[
                    Paragraph(
                        number="1",
                        text="Information shall include:",
                        points=[
                            Point(
                                marker="(b)",
                                style="lower_alpha",
                                text="the applicable supervisory regime and information on the liability regime with respect to the following:",
                                subpoints=[
                                    Point(
                                        marker="(i)",
                                        style="lower_roman",
                                        text="the party issuing the electronic identification means; and",
                                    ),
                                    Point(
                                        marker="(ii)",
                                        style="lower_roman",
                                        text="the party operating the authentication procedure.",
                                    ),
                                ],
                            )
                        ],
                    )
                ],
                notes=[],
            )
        ],
    )

    result = generate_markdown(document)

    assert "   - (b) the applicable supervisory regime" in result
    assert (
        "      - (i) the party issuing the electronic identification means; and"
        in result
    )
    assert "      - (ii) the party operating the authentication procedure." in result


def test_generate_markdown_dict_paragraph_points_keep_symbol_and_unordered_list() -> (
    None
):
    parsed_data = {
        "title": "REGULATION 789",
        "articles": [
            {
                "id": "Article 4",
                "title": "Controls",
                "body": "legacy",
                "paragraphs": [
                    {
                        "number": "1",
                        "text": "Requirements include:",
                        "points": [
                            {
                                "marker": "(i)",
                                "style": "lower_roman",
                                "text": "access control",
                                "subpoints": [],
                            },
                            {
                                "marker": "(ii)",
                                "style": "lower_roman",
                                "text": "logging",
                                "subpoints": [],
                            },
                        ],
                    }
                ],
                "notes": [],
            }
        ],
        "annexes": [],
    }

    result = generate_markdown(parsed_data)

    assert "1. Requirements include:" in result
    assert "   - (i) access control" in result
    assert "   - (ii) logging" in result
    assert "legacy" not in result


def test_generate_markdown_does_not_number_unnumbered_paragraphs() -> None:
    document = EurLexDocument(
        title="REGULATION 999",
        articles=[
            Section(
                id="Article 5",
                title="Plain text",
                body="",
                paragraphs=[
                    Paragraph(number="", text="First unnumbered paragraph.", points=[]),
                    Paragraph(
                        number="",
                        text="Second unnumbered paragraph.",
                        points=[
                            Point(marker="(a)", style="lower_alpha", text="detail one"),
                        ],
                    ),
                ],
                notes=[],

            )
        ],
    )

    result = generate_markdown(document)

    assert "First unnumbered paragraph." in result
    assert "Second unnumbered paragraph." in result
    assert "1. First unnumbered paragraph." not in result
    assert "1. Second unnumbered paragraph." not in result
    assert "- (a) detail one" in result


def test_generate_markdown_dash_enumeration_uses_native_sublist_marker() -> None:
    document = EurLexDocument(
        title="REGULATION 1000",
        articles=[
            Section(
                id="Article 6",
                title="Dash list",
                body="",
                paragraphs=[
                    Paragraph(
                        number="3",
                        text="Monitoring shall include:",
                        points=[
                            Point(
                                marker="—", style="dash", text="stakeholder feedback"
                            ),
                            Point(marker="-", style="dash", text="incident follow-up"),
                        ],
                    )
                ],
                notes=[],

            )
        ],
    )

    result = generate_markdown(document)

    assert "3. Monitoring shall include:" in result
    assert "   - stakeholder feedback" in result
    assert "   - incident follow-up" in result
    assert "   - — stakeholder feedback" not in result
    assert "   - - incident follow-up" not in result


def test_generate_markdown_renders_inline_dash_enumeration_inside_point() -> None:
    document = EurLexDocument(
        title="REGULATION 1001",
        articles=[
            Section(
                id="Article 7",
                title="Nested list",
                body="",
                paragraphs=[
                    Paragraph(
                        number="4",
                        text="The periodic review shall consider:",
                        points=[
                            Point(
                                marker="(c)",
                                style="lower_alpha",
                                text=(
                                    "the following aspects: — requests for clarification; "
                                    "— feedback from stakeholders; — responsiveness."
                                ),
                            )
                        ],
                    )
                ],
                notes=[],

            )
        ],
    )

    result = generate_markdown(document)

    assert "   - (c) the following aspects:" in result
    assert "      - requests for clarification" in result
    assert "      - feedback from stakeholders" in result
    assert "      - responsiveness." in result


def test_generate_markdown_renders_multi_level_nested_dash_lists() -> None:
    document = EurLexDocument(
        title="REGULATION 1002",
        articles=[
            Section(
                id="Article 8",
                title="Deep nested list",
                body="",
                paragraphs=[
                    Paragraph(
                        number="5",
                        text="Evidence shall include:",
                        points=[
                            Point(
                                marker="(a)",
                                style="lower_alpha",
                                text=(
                                    "technical documentation: — architecture information; "
                                    "— controls and assurance levels; — rationale: "
                                    "— mapping to components; — risk coverage."
                                ),
                            )
                        ],
                    )
                ],
                notes=[],

            )
        ],
    )

    result = generate_markdown(document)

    assert "   - (a) technical documentation:" in result
    assert "      - architecture information" in result
    assert "      - controls and assurance levels" in result
    assert "      - rationale:" in result
    assert "         - mapping to components" in result
    assert "         - risk coverage." in result


def test_generate_markdown_renders_final_provisions_and_signature() -> None:
    document = EurLexDocument(
        title="REGULATION FINAL",
        articles=[
            Section(
                id="Article 1",
                title="Scope",
                body="1. This Regulation applies.",

            )
        ],
        final_text=(
            "This Regulation shall be binding in its entirety and directly applicable in all Member States.\n\n"
            "Done at Brussels, 28 November 2024."
        ),
        signature_lines=["For the Commission", "The President", "Ursula VON DER LEYEN"],
    )

    result = generate_markdown(document)

    assert "## Final Provisions" in result
    assert "Done at Brussels, 28 November 2024." in result
    assert "- For the Commission" in result
    assert "- The President" in result
    assert "- Ursula VON DER LEYEN" in result


def test_generate_markdown_annex_heading_includes_annex_title() -> None:
    document = EurLexDocument(
        title="REGULATION ANNEX",
        annexes=[
            Section(
                id="ANNEX I",
                title="RISK REGISTER",
                body="#### SECTION I - General items\n\nText.",

            )
        ],
    )

    result = generate_markdown(document)

    assert "### ANNEX I - RISK REGISTER" in result
    assert "#### SECTION I - General items" in result
