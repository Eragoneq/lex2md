"""Tests for Obsidian-flavored markdown features.

Covers:
- Block link generation on paragraphs / points (not headings)
- Footnote namespacing to avoid ^id collisions
- Wikilink vs standard markdown link styles
- Semantic link resolution for Article and Annex citations
- External document exclusion ("of Regulation ...")
"""
from __future__ import annotations

from lex2md.markdown import generate_markdown
from lex2md.models import EurLexDocument, Note, Paragraph, Point, Section


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(
    articles: list[Section] | None = None,
    annexes: list[Section] | None = None,
    preamble: str = "",
    preamble_notes: list[Note] | None = None,
) -> EurLexDocument:
    return EurLexDocument(
        title="TEST REGULATION",
        preamble=preamble,
        preamble_notes=preamble_notes or [],
        articles=articles or [],
        annexes=annexes or [],
        celex="32024R0001",
        language="en",
    )


def _article(
    num: str,
    title: str = "",
    paragraphs: list[Paragraph] | None = None,
    body: str = "",
    notes: list[Note] | None = None,
) -> Section:
    return Section(
        id=f"Article {num}",
        title=title,
        body=body,
        paragraphs=paragraphs or [],
        notes=notes or [],
        anchor=f"article-{num.lower()}",
    )


def _annex(
    num: str,
    title: str = "",
    body: str = "",
    paragraphs: list[Paragraph] | None = None,
) -> Section:
    return Section(
        id=f"ANNEX {num}",
        title=title,
        body=body,
        paragraphs=paragraphs or [],
        anchor=f"annex-{num.lower()}",
    )


# ===================================================================
# 1. Block links — paragraphs and points get ^id, headings do NOT
# ===================================================================


class TestBlockLinks:
    """Block link IDs are appended to paragraph and point lines only."""

    def test_heading_has_no_block_link(self) -> None:
        doc = _make_doc(articles=[_article("1", "Subject", body="Body.")])
        result = generate_markdown(doc, add_block_links=True)
        # Heading should NOT have ^article-1
        for line in result.splitlines():
            if line.startswith("###"):
                assert "^article-1" not in line

    def test_paragraph_gets_block_link(self) -> None:
        doc = _make_doc(articles=[
            _article("3", paragraphs=[
                Paragraph(number="1", text="First paragraph.", points=[]),
            ]),
        ])
        result = generate_markdown(doc, add_block_links=True)
        assert "1. First paragraph. ^article-3-1" in result

    def test_point_gets_block_link(self) -> None:
        doc = _make_doc(articles=[
            _article("3", paragraphs=[
                Paragraph(
                    number="1",
                    text="Shall include:",
                    points=[
                        Point(marker="(a)", style="lower_alpha", text="governance rules"),
                    ],
                ),
            ]),
        ])
        result = generate_markdown(doc, add_block_links=True)
        assert "^article-3-1-a" in result

    def test_subpoint_gets_block_link(self) -> None:
        doc = _make_doc(articles=[
            _article("3", paragraphs=[
                Paragraph(
                    number="1",
                    text="Information:",
                    points=[
                        Point(
                            marker="(b)",
                            style="lower_alpha",
                            text="supervisory regime:",
                            subpoints=[
                                Point(marker="(i)", style="lower_roman", text="issuing party"),
                            ],
                        ),
                    ],
                ),
            ]),
        ])
        result = generate_markdown(doc, add_block_links=True)
        assert "^article-3-1-b-i" in result

    def test_no_html_anchors_emitted(self) -> None:
        doc = _make_doc(articles=[_article("1", body="Body.")])
        result = generate_markdown(doc, add_block_links=True)
        assert '<a id="article-1"></a>' not in result


# ===================================================================
# 2. Footnote namespacing — [^id] → [^fn-id] when block links active
# ===================================================================


class TestFootnoteNamespacing:
    """Footnotes are prefixed with 'fn-' when block links are active to
    avoid collision with Obsidian ^id block anchors."""

    def test_footnote_definition_namespaced(self) -> None:
        doc = _make_doc(
            articles=[_article("1", body="Text [^1].", notes=[Note(id="1", text="Footnote.")])],
        )
        result = generate_markdown(doc, add_block_links=True)
        assert "[^fn-1]: Footnote." in result

    def test_footnote_ref_in_body_namespaced(self) -> None:
        doc = _make_doc(
            articles=[_article("1", body="Text [^1].", notes=[Note(id="1", text="Footnote.")])],
        )
        result = generate_markdown(doc, add_block_links=True)
        assert "Text [^fn-1]." in result

    def test_footnote_ref_in_paragraph_namespaced(self) -> None:
        doc = _make_doc(articles=[
            _article("2", paragraphs=[
                Paragraph(number="1", text="Some text [^3].", points=[]),
            ], notes=[Note(id="3", text="A note.")]),
        ])
        result = generate_markdown(doc, add_block_links=True)
        assert "[^fn-3]" in result
        assert "[^fn-3]: A note." in result

    def test_footnote_not_namespaced_without_block_links(self) -> None:
        doc = _make_doc(
            articles=[_article("1", body="Text [^1].", notes=[Note(id="1", text="Footnote.")])],
        )
        result = generate_markdown(doc, add_block_links=False)
        assert "[^1]: Footnote." in result
        assert "fn-" not in result

    def test_preamble_footnotes_namespaced(self) -> None:
        doc = _make_doc(
            preamble="Preamble text [^1].",
            preamble_notes=[Note(id="1", text="Preamble note.")],
        )
        result = generate_markdown(doc, add_block_links=True)
        assert "[^fn-1]: Preamble note." in result


# ===================================================================
# 3. Wikilinks vs standard markdown links
# ===================================================================


class TestWikilinks:
    """Navigation and intra-document links use [[#anchor|label]] style."""

    def test_navigation_uses_wikilinks(self) -> None:
        doc = _make_doc(articles=[_article("1", "Subject", body="Body.")])
        result = generate_markdown(doc, links_style="wikilinks")
        assert "[[#article-1|Article 1 - Subject]]" in result

    def test_no_navigation_in_standard_markdown(self) -> None:
        doc = _make_doc(articles=[_article("1", "Subject", body="Body.")])
        result = generate_markdown(doc)
        assert "## Navigation" not in result

    def test_preamble_intra_links_use_wikilinks(self) -> None:
        doc = _make_doc(
            articles=[_article("1", body="Body.")],
            preamble="See Article 1.",
        )
        result = generate_markdown(doc, links_style="wikilinks")
        assert "[[#article-1|Article 1]]" in result

    def test_annex_intra_links_use_wikilinks(self) -> None:
        doc = _make_doc(
            annexes=[_annex("IV", body="Content.")],
            preamble="See ANNEX IV.",
        )
        result = generate_markdown(doc, links_style="wikilinks")
        assert "[[#annex-iv|ANNEX IV]]" in result


# ===================================================================
# 4. Semantic link resolution — the core feature
# ===================================================================


class TestSemanticLinkResolution:
    """Test _resolve_semantic_references via generate_markdown with
    resolve_semantic_links=True."""

    # --- Simple article references ---

    def test_simple_article_reference(self) -> None:
        doc = _make_doc(
            articles=[_article("3", body="Body.")],
            preamble="See Article 3.",
        )
        result = generate_markdown(doc, resolve_semantic_links=True)
        assert "[Article 3](#article-3)" in result

    def test_simple_article_reference_wikilinks(self) -> None:
        doc = _make_doc(
            articles=[_article("3", body="Body.")],
            preamble="See Article 3.",
        )
        result = generate_markdown(doc, resolve_semantic_links=True, links_style="wikilinks")
        assert "[[#article-3|Article 3]]" in result

    # --- Annex references ---

    def test_annex_reference(self) -> None:
        """'Annex IV' → link to annex-iv."""
        doc = _make_doc(
            annexes=[_annex("IV", body="Content.")],
            preamble="See Annex IV for details.",
        )
        result = generate_markdown(doc, resolve_semantic_links=True)
        assert "[Annex IV](#annex-iv)" in result

    def test_annex_reference_uppercase(self) -> None:
        """'ANNEX IV' → link to annex-iv."""
        doc = _make_doc(
            annexes=[_annex("IV", body="Content.")],
            preamble="See ANNEX IV for details.",
        )
        result = generate_markdown(doc, resolve_semantic_links=True)
        assert "[ANNEX IV](#annex-iv)" in result

    # --- Article with parenthesized qualifiers ---

    def test_article_with_single_qualifier(self) -> None:
        """'Article 5a(23)' → block link to ^article-5a-23."""
        doc = _make_doc(
            articles=[_article("5a", body="Body.")],
            preamble="According to Article 5a(23).",
        )
        result = generate_markdown(
            doc, resolve_semantic_links=True, add_block_links=True,
        )
        assert "[Article 5a(23)](#^article-5a-23)" in result

    def test_article_with_double_qualifier(self) -> None:
        """'Article 3(1)(a)' → block link to ^article-3-1-a."""
        doc = _make_doc(
            articles=[_article("3", body="Body.")],
            preamble="As stated in Article 3(1)(a).",
        )
        result = generate_markdown(
            doc, resolve_semantic_links=True, add_block_links=True,
        )
        assert "[Article 3(1)(a)](#^article-3-1-a)" in result

    def test_article_qualifier_wikilinks(self) -> None:
        """'Article 3(1)(a)' with wikilinks → [[#^article-3-1-a|Article 3(1)(a)]]."""
        doc = _make_doc(
            articles=[_article("3", body="Body.")],
            preamble="As stated in Article 3(1)(a).",
        )
        result = generate_markdown(
            doc,
            resolve_semantic_links=True,
            add_block_links=True,
            links_style="wikilinks",
        )
        assert "[[#^article-3-1-a|Article 3(1)(a)]]" in result

    # --- "paragraph N, point (x)" style ---

    def test_article_paragraph_point_style(self) -> None:
        """'Article 3 paragraph 5, point (a)' → block link."""
        doc = _make_doc(
            articles=[_article("3", body="Body.")],
            preamble="Refer to Article 3 paragraph 5, point (a).",
        )
        result = generate_markdown(
            doc, resolve_semantic_links=True, add_block_links=True,
        )
        assert "[Article 3 paragraph 5, point (a)](#^article-3-5-a)" in result

    def test_article_paragraph_point_style_wikilinks(self) -> None:
        """'Article 3 paragraph 5, point (a)' → block link, including inside article bodies."""
        doc = _make_doc(
            articles=[
                _article("3", body="Body. Article 6 paragraph 2, point (b)."),
                _article("6", body="Body of Article 6."),
            ],
            preamble="Refer to Article 3 paragraph 5, point (a).",
        )
        result = generate_markdown(
            doc, resolve_semantic_links=True, add_block_links=True, links_style="wikilinks",
        )
        assert "[[#^article-3-5-a|Article 3 paragraph 5, point (a)]]" in result
        assert "[[#^article-6-2-b|Article 6 paragraph 2, point (b)]]" in result

    def test_article_paragraph_only(self) -> None:
        """'Article 3 paragraph 5' → block link with paragraph only."""
        doc = _make_doc(
            articles=[_article("3", body="Body.")],
            preamble="Refer to Article 3 paragraph 5.",
        )
        result = generate_markdown(
            doc, resolve_semantic_links=True, add_block_links=True,
        )
        assert "[Article 3 paragraph 5](#^article-3-5)" in result

    # --- Compound "Articles X and Y" ---

    def test_articles_compound(self) -> None:
        """'Articles 5c(4) and 5e(2)' → two separate links."""
        doc = _make_doc(
            articles=[
                _article("5c", body="Body 5c."),
                _article("5e", body="Body 5e."),
            ],
            preamble="As per Articles 5c(4) and 5e(2).",
        )
        result = generate_markdown(
            doc, resolve_semantic_links=True, add_block_links=True,
        )
        assert "[5c(4)](#^article-5c-4)" in result
        assert "[5e(2)](#^article-5e-2)" in result
        assert "Articles" in result

    def test_articles_compound_wikilinks(self) -> None:
        """'Articles 5c(4) and 5e(2)' with wikilinks."""
        doc = _make_doc(
            articles=[
                _article("5c", body="Body 5c."),
                _article("5e", body="Body 5e."),
            ],
            preamble="As per Articles 5c(4) and 5e(2).",
        )
        result = generate_markdown(
            doc,
            resolve_semantic_links=True,
            add_block_links=True,
            links_style="wikilinks",
        )
        assert "[[#^article-5c-4|5c(4)]]" in result
        assert "[[#^article-5e-2|5e(2)]]" in result

    # --- Annex with qualifier ---

    def test_annex_with_point_qualifier(self) -> None:
        """'Annex IV, point 1' → block link."""
        doc = _make_doc(
            annexes=[_annex("IV", body="Content.")],
            preamble="As set out in Annex IV, point 1.",
        )
        result = generate_markdown(
            doc, resolve_semantic_links=True, add_block_links=True,
        )
        assert "[Annex IV, point 1](#^annex-iv-1)" in result

    def test_annex_with_parenthesized_point(self) -> None:
        """'Annex IV, point (a)' → block link."""
        doc = _make_doc(
            annexes=[_annex("IV", body="Content.")],
            preamble="As set out in Annex IV, point (a).",
        )
        result = generate_markdown(
            doc, resolve_semantic_links=True, add_block_links=True,
        )
        assert "[Annex IV, point (a)](#^annex-iv-a)" in result

    # --- Qualifiers without block links → link to section only ---

    def test_qualifier_falls_back_to_section_without_block_links(self) -> None:
        """When block links are off, 'Article 3(1)(a)' links to article-3 level only."""
        doc = _make_doc(
            articles=[_article("3", body="Body.")],
            preamble="As stated in Article 3(1)(a).",
        )
        result = generate_markdown(
            doc, resolve_semantic_links=True, add_block_links=False,
        )
        assert "[Article 3(1)(a)](#article-3)" in result

    # --- External document exclusion ---

    def test_external_regulation_not_linked(self) -> None:
        """'Article 3 of Regulation (EU)...' should NOT be linked."""
        doc = _make_doc(
            articles=[_article("3", body="Body.")],
            preamble="Article 3 of Regulation (EU) 2016/679 applies.",
        )
        result = generate_markdown(doc, resolve_semantic_links=True)
        # The preamble line should remain plain (external reference)
        assert "Article 3 of Regulation (EU) 2016/679 applies." in result

    def test_external_directive_not_linked(self) -> None:
        """'Article 5 of Directive...' should NOT be linked."""
        doc = _make_doc(
            articles=[_article("5", body="Body.")],
            preamble="Article 5 of Directive 2014/53/EU applies.",
        )
        result = generate_markdown(doc, resolve_semantic_links=True)
        # The preamble line should remain plain (external reference)
        assert "Article 5 of Directive 2014/53/EU applies." in result

    def test_external_annex_regulation_not_linked(self) -> None:
        """'Annex IV of Regulation...' should NOT be linked."""
        doc = _make_doc(
            annexes=[_annex("IV", body="Content.")],
            preamble="Annex IV of Regulation (EU) 2019/881.",
        )
        result = generate_markdown(doc, resolve_semantic_links=True)
        assert "[Annex IV]" not in result

    # --- Edge cases ---

    def test_unknown_article_not_linked(self) -> None:
        """References to articles not in this document are left plain."""
        doc = _make_doc(
            articles=[_article("1", body="Body.")],
            preamble="See Article 99.",
        )
        result = generate_markdown(doc, resolve_semantic_links=True)
        assert "[Article 99]" not in result
        assert "Article 99" in result

    def test_already_linked_not_double_linked(self) -> None:
        """Don't double-link something already inside []."""
        doc = _make_doc(
            articles=[_article("3", body="Body.")],
            preamble="See [Article 3](#article-3) again.",
        )
        result = generate_markdown(doc, resolve_semantic_links=True)
        # Should not produce [[ or nested links
        assert "[[Article 3]" not in result
        # The preamble line should remain unchanged (not double-wrapped)
        assert "See [Article 3](#article-3) again." in result

    def test_multiple_references_in_same_text(self) -> None:
        """Multiple distinct references in the same string."""
        doc = _make_doc(
            articles=[
                _article("1", body="Body 1."),
                _article("3", body="Body 3."),
            ],
            annexes=[_annex("IV", body="Content.")],
            preamble="Article 1, Article 3 and ANNEX IV are relevant.",
        )
        result = generate_markdown(doc, resolve_semantic_links=True)
        assert "[Article 1](#article-1)" in result
        assert "[Article 3](#article-3)" in result
        assert "[ANNEX IV](#annex-iv)" in result

    def test_article_with_letter_suffix(self) -> None:
        """'Article 5a' → link to article-5a."""
        doc = _make_doc(
            articles=[_article("5a", body="Body.")],
            preamble="See Article 5a.",
        )
        result = generate_markdown(doc, resolve_semantic_links=True)
        assert "[Article 5a](#article-5a)" in result
