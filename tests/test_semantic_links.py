from __future__ import annotations

import pytest

from lex2md.markdown import (
    RenderConfig,
    _extract_qualifier_parts,
    _format_link,
    _is_external_reference,
    _resolve_semantic_references,
    _slugify,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(*, links_style: str = "wikilinks", add_block_links: bool = False) -> RenderConfig:
    return RenderConfig(
        links_style=links_style,
        add_block_links=add_block_links,
        resolve_semantic_links=True,
    )


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    @pytest.mark.parametrize(
        "input_text, expected_slug",
        [
            ("Article 1", "article-1"),
            ("Article 5a", "article-5a"),
            ("Article 5c", "article-5c"),
            ("ANNEX I", "annex-i"),
            ("ANNEX IV", "annex-iv"),
            ("Annex IV A", "annex-iv-a"),
            ("Article 10", "article-10"),
            ("Article 100", "article-100"),
            ("  Article 3  ", "article-3"),
            ("ANNEX II", "annex-ii"),
        ],
    )
    def test_slugify(self, input_text: str, expected_slug: str) -> None:
        assert _slugify(input_text) == expected_slug


# ---------------------------------------------------------------------------
# _extract_qualifier_parts
# ---------------------------------------------------------------------------


class TestExtractQualifierParts:
    @pytest.mark.parametrize(
        "qualifier, expected_parts",
        [
            ("(1)(a)", ["1", "a"]),
            ("(1)", ["1"]),
            ("(a)", ["a"]),
            ("(1)(a)(i)", ["1", "a", "i"]),
            ("(3), point (b)", ["3", "b"]),
            ("(2)(a), point (i)", ["2", "a", "i"]),
            (" point (1)", ["1"]),
            (", point (46)", ["46"]),
            (", point 1", ["1"]),
            (" paragraph 5, point (a)", ["5", "a"]),
            (" paragraph 5", ["5"]),
            (" point (a)", ["a"]),
            (" point a", ["a"]),
            (", point 1", ["1"]),
            (", point (a)", ["a"]),
            (" paragraph 10, point (b)", ["10", "b"]),
            ("(23)", ["23"]),
            ("(4)", ["4"]),
            ("(a)(i)", ["a", "i"]),
            ("(iv)", ["iv"]),
        ],
    )
    def test_extract_qualifier_parts(self, qualifier: str, expected_parts: list[str]) -> None:
        assert _extract_qualifier_parts(qualifier) == expected_parts


# ---------------------------------------------------------------------------
# _is_external_reference
# ---------------------------------------------------------------------------


class TestIsExternalReference:
    @pytest.mark.parametrize(
        "source, match_end, expected",
        [
            ("Article 1 of Regulation 2024/123", 9, True),
            ("Article 1 of Directive 2024/123", 9, True),
            ("Article 1 of Decision 2024/123", 9, True),
            ("Article 1 of Delegated Regulation", 9, True),
            ("Article 1 of Implementing Decision", 9, True),
            ("Article 1 of Commission Regulation", 9, True),
            ("Article 1 of Council Directive", 9, True),
            ("Article 1 of European Regulation", 9, True),
            ("Article 2 point (1), of Directive (EU) 2016/943", 20, True),
            ("Article 1 shall apply", 9, False),
            ("Article 1.", 9, False),
            ("Article 1 and Article 2", 9, False),
            ("Article 1(1)", 9, False),
        ],
    )
    def test_is_external_reference(self, source: str, match_end: int, expected: bool) -> None:
        assert _is_external_reference(source, match_end) == expected


# ---------------------------------------------------------------------------
# _format_link
# ---------------------------------------------------------------------------


class TestFormatLink:
    @pytest.mark.parametrize(
        "label, target, style, expected",
        [
            ("Article 1", "Article 1 - Subject", "wikilinks", "[[#Article 1 - Subject|Article 1]]"),
            ("Article 1", "article-1", "wikilinks", "[[#article-1|Article 1]]"),
            ("Article 1", "^article-1-1-a", "wikilinks", "[[#^article-1-1-a|Article 1]]"),
            ("Article 1", "Article 1", "markdown", "[Article 1](#Article%201)"),
            ("Article 1", "^article-1-1-a", "markdown", "[Article 1](#^article-1-1-a)"),
            ("Annex IV", "ANNEX IV - List", "wikilinks", "[[#ANNEX IV - List|Annex IV]]"),
            ("Annex IV", "^annex-iv-1", "wikilinks", "[[#^annex-iv-1|Annex IV]]"),
        ],
    )
    def test_format_link(self, label: str, target: str, style: str, expected: str) -> None:
        assert _format_link(label, target, style) == expected


# ---------------------------------------------------------------------------
# _resolve_semantic_references — Article references (wikilinks, no block links)
# ---------------------------------------------------------------------------


class TestResolveSemanticArticlesWikilinks:
    """Article reference → wikilink (heading-level) resolution tests."""

    @pytest.mark.parametrize(
        "input_text, article_ids, heading_map, expected",
        [
            # Simple article references
            (
                "See Article 1 for details.",
                {"Article 1"},
                {"Article 1": "Article 1 - Subject"},
                "See [[#Article 1 - Subject|Article 1]] for details.",
            ),
            (
                "Article 5a provides that",
                {"Article 5a"},
                {"Article 5a": "Article 5a - Scope"},
                "[[#Article 5a - Scope|Article 5a]] provides that",
            ),
            (
                "Under Article 3 the rules apply.",
                {"Article 3"},
                {"Article 3": "Article 3 - Definitions"},
                "Under [[#Article 3 - Definitions|Article 3]] the rules apply.",
            ),
            # Article with parenthetical qualifier (no block links → heading link)
            (
                "Article 1(1) states",
                {"Article 1"},
                {"Article 1": "Article 1 - Subject"},
                "[[#Article 1 - Subject|Article 1(1)]] states",
            ),
            (
                "Article 5c(4) requires",
                {"Article 5c"},
                {"Article 5c": "Article 5c - Penalties"},
                "[[#Article 5c - Penalties|Article 5c(4)]] requires",
            ),
            # Article with paragraph/point qualifier (no block links → heading link)
            (
                "Article 3 paragraph 5, point (a) defines",
                {"Article 3"},
                {"Article 3": "Article 3 - Definitions"},
                "[[#Article 3 - Definitions|Article 3 paragraph 5, point (a)]] defines",
            ),
            # Unknown article → no link
            (
                "See Article 99 for details.",
                {"Article 1"},
                {"Article 1": "Article 1 - Subject"},
                "See Article 99 for details.",
            ),
            # External reference → no link
            (
                "Article 1 of Regulation 2024/123",
                {"Article 1"},
                {"Article 1": "Article 1 - Subject"},
                "Article 1 of Regulation 2024/123",
            ),
            # Already linked → no double-link (guard prevents re-matching inside wikilinks)
            (
                "[[#Article 1 - Subject|Article 1]]",
                {"Article 1"},
                {"Article 1": "Article 1 - Subject"},
                "[[#Article 1 - Subject|Article 1]]",
            ),
            # Multiple articles in same text
            (
                "Article 1 and Article 2 apply.",
                {"Article 1", "Article 2"},
                {"Article 1": "Article 1 - Subject", "Article 2": "Article 2 - Scope"},
                "[[#Article 1 - Subject|Article 1]] and [[#Article 2 - Scope|Article 2]] apply.",
            ),
        ],
    )
    def test_resolve_articles_wikilinks(
        self,
        input_text: str,
        article_ids: set[str],
        heading_map: dict[str, str],
        expected: str,
    ) -> None:
        config = _make_config(links_style="wikilinks", add_block_links=False)
        result = _resolve_semantic_references(
            input_text,
            article_ids,
            set(),
            config,
            heading_map=heading_map,
        )
        assert result == expected


# ---------------------------------------------------------------------------
# _resolve_semantic_references — Article references (wikilinks + block links)
# ---------------------------------------------------------------------------


class TestResolveSemanticArticlesBlockLinks:
    """Article reference → block-level link resolution tests."""

    @pytest.mark.parametrize(
        "input_text, article_ids, heading_map, expected",
        [
            # Simple article (no qualifier) → heading link
            (
                "See Article 1 for details.",
                {"Article 1"},
                {"Article 1": "Article 1 - Subject"},
                "See [[#Article 1 - Subject|Article 1]] for details.",
            ),
            # Article with (1)(a) → block link
            (
                "Article 1(1)(a) states",
                {"Article 1"},
                {"Article 1": "Article 1 - Subject"},
                "[[#^article-1-1-a|Article 1(1)(a)]] states",
            ),
            # Article with (4) → block link
            (
                "Article 5c(4) requires",
                {"Article 5c"},
                {"Article 5c": "Article 5c - Penalties"},
                "[[#^article-5c-4|Article 5c(4)]] requires",
            ),
            # Article with paragraph/point → block link
            (
                "Article 3 paragraph 5, point (a) defines",
                {"Article 3"},
                {"Article 3": "Article 3 - Definitions"},
                "[[#^article-3-5-a|Article 3 paragraph 5, point (a)]] defines",
            ),
            # Article with paragraph only → block link
            (
                "Article 3 paragraph 5 defines",
                {"Article 3"},
                {"Article 3": "Article 3 - Definitions"},
                "[[#^article-3-5|Article 3 paragraph 5]] defines",
            ),
            # Article with point only → block link (standalone point is now matched)
            (
                "Article 3 point (a) defines",
                {"Article 3"},
                {"Article 3": "Article 3 - Definitions"},
                "[[#^article-3-a|Article 3 point (a)]] defines",
            ),
            # Article with (1)(a)(i) → deep block link
            (
                "Article 1(1)(a)(i) specifies",
                {"Article 1"},
                {"Article 1": "Article 1 - Subject"},
                "[[#^article-1-1-a-i|Article 1(1)(a)(i)]] specifies",
            ),
            # Unknown article → no link even with block links enabled
            (
                "Article 99(1) states",
                {"Article 1"},
                {"Article 1": "Article 1 - Subject"},
                "Article 99(1) states",
            ),
        ],
    )
    def test_resolve_articles_block_links(
        self,
        input_text: str,
        article_ids: set[str],
        heading_map: dict[str, str],
        expected: str,
    ) -> None:
        config = _make_config(links_style="wikilinks", add_block_links=True)
        result = _resolve_semantic_references(
            input_text,
            article_ids,
            set(),
            config,
            heading_map=heading_map,
        )
        assert result == expected


# ---------------------------------------------------------------------------
# _resolve_semantic_references — Annex references (wikilinks, no block links)
# ---------------------------------------------------------------------------


class TestResolveSemanticAnnexWikilinks:
    """Annex reference → wikilink resolution tests."""

    @pytest.mark.parametrize(
        "input_text, annex_ids, heading_map, expected",
        [
            # Simple annex reference
            (
                "See Annex IV for the list.",
                {"ANNEX IV"},
                {"ANNEX IV": "ANNEX IV - List"},
                "See [[#ANNEX IV - List|Annex IV]] for the list.",
            ),
            (
                "ANNEX I contains items.",
                {"ANNEX I"},
                {"ANNEX I": "ANNEX I - Risk Register"},
                "[[#ANNEX I - Risk Register|ANNEX I]] contains items.",
            ),
            # Annex with title variant
            (
                "See Annex II for details.",
                {"ANNEX II"},
                {"ANNEX II": "ANNEX II - Criteria"},
                "See [[#ANNEX II - Criteria|Annex II]] for details.",
            ),
            # Annex with point qualifier (no block links → heading link, trailing space captured)
            (
                "Annex IV, point 1 specifies",
                {"ANNEX IV"},
                {"ANNEX IV": "ANNEX IV - List"},
                "[[#ANNEX IV - List|Annex IV, point 1 ]]specifies",
            ),
            # Unknown annex → no link
            (
                "See Annex IX for details.",
                {"ANNEX IV"},
                {"ANNEX IV": "ANNEX IV - List"},
                "See Annex IX for details.",
            ),
            # External reference → no link
            (
                "Annex IV of Directive 2024/123",
                {"ANNEX IV"},
                {"ANNEX IV": "ANNEX IV - List"},
                "Annex IV of Directive 2024/123",
            ),
        ],
    )
    def test_resolve_annex_wikilinks(
        self,
        input_text: str,
        annex_ids: set[str],
        heading_map: dict[str, str],
        expected: str,
    ) -> None:
        config = _make_config(links_style="wikilinks", add_block_links=False)
        result = _resolve_semantic_references(
            input_text,
            set(),
            annex_ids,
            config,
            heading_map=heading_map,
        )
        assert result == expected


# ---------------------------------------------------------------------------
# _resolve_semantic_references — Annex references (wikilinks + block links)
# ---------------------------------------------------------------------------


class TestResolveSemanticAnnexBlockLinks:
    """Annex reference → block-level link resolution tests."""

    @pytest.mark.parametrize(
        "input_text, annex_ids, heading_map, expected",
        [
            # Simple annex (no qualifier) → heading link
            (
                "See Annex IV for the list.",
                {"ANNEX IV"},
                {"ANNEX IV": "ANNEX IV - List"},
                "See [[#ANNEX IV - List|Annex IV]] for the list.",
            ),
            # Annex with ", point 1" → block link (trailing space captured)
            (
                "Annex IV, point 1 specifies",
                {"ANNEX IV"},
                {"ANNEX IV": "ANNEX IV - List"},
                "[[#^annex-iv-1|Annex IV, point 1 ]]specifies",
            ),
            # Annex with ", point (a)" → block link
            (
                "Annex IV, point (a) defines",
                {"ANNEX IV"},
                {"ANNEX IV": "ANNEX IV - List"},
                "[[#^annex-iv-a|Annex IV, point (a)]] defines",
            ),
            # Annex with (1)(a) style → block link
            (
                "Annex IV(1)(a) specifies",
                {"ANNEX IV"},
                {"ANNEX IV": "ANNEX IV - List"},
                "[[#^annex-iv-1-a|Annex IV(1)(a)]] specifies",
            ),
            # Annex with title variant (Annex IV A) (trailing space captured)
            (
                "Annex IV A, point 2 describes",
                {"ANNEX IV A"},
                {"ANNEX IV A": "ANNEX IV A - Sub-list"},
                "[[#^annex-iv-a-2|Annex IV A, point 2 ]]describes",
            ),
        ],
    )
    def test_resolve_annex_block_links(
        self,
        input_text: str,
        annex_ids: set[str],
        heading_map: dict[str, str],
        expected: str,
    ) -> None:
        config = _make_config(links_style="wikilinks", add_block_links=True)
        result = _resolve_semantic_references(
            input_text,
            set(),
            annex_ids,
            config,
            heading_map=heading_map,
        )
        assert result == expected


# ---------------------------------------------------------------------------
# _resolve_semantic_references — Markdown style links
# ---------------------------------------------------------------------------


class TestResolveSemanticMarkdownStyle:
    """Semantic link resolution with standard markdown link style."""

    @pytest.mark.parametrize(
        "input_text, article_ids, annex_ids, heading_map, add_block_links, expected",
        [
            # Article → markdown link
            (
                "See Article 1 for details.",
                {"Article 1"},
                set(),
                {"Article 1": "Article 1 - Subject"},
                False,
                "See [Article 1](#Article%201%20-%20Subject) for details.",
            ),
            # Article with qualifier → markdown block link
            (
                "Article 1(1)(a) states",
                {"Article 1"},
                set(),
                {"Article 1": "Article 1 - Subject"},
                True,
                "[Article 1(1)(a)](#^article-1-1-a) states",
            ),
            # Annex → markdown link
            (
                "See Annex IV for info.",
                set(),
                {"ANNEX IV"},
                {"ANNEX IV": "ANNEX IV - List"},
                False,
                "See [Annex IV](#ANNEX%20IV%20-%20List) for info.",
            ),
            # Annex with point → markdown block link (trailing space captured)
            (
                "Annex IV, point 1 specifies",
                set(),
                {"ANNEX IV"},
                {"ANNEX IV": "ANNEX IV - List"},
                True,
                "[Annex IV, point 1 ](#^annex-iv-1)specifies",
            ),
        ],
    )
    def test_resolve_markdown_style(
        self,
        input_text: str,
        article_ids: set[str],
        annex_ids: set[str],
        heading_map: dict[str, str],
        add_block_links: bool,
        expected: str,
    ) -> None:
        config = _make_config(links_style="markdown", add_block_links=add_block_links)
        result = _resolve_semantic_references(
            input_text,
            article_ids,
            annex_ids,
            config,
            heading_map=heading_map,
        )
        assert result == expected


# ---------------------------------------------------------------------------
# _resolve_semantic_references — Edge cases and combined scenarios
# ---------------------------------------------------------------------------


class TestResolveSemanticEdgeCases:
    """Edge cases and combined article + annex resolution tests."""

    @pytest.mark.parametrize(
        "input_text, article_ids, annex_ids, heading_map, add_block_links, expected",
        [
            # Both article and annex in same text
            (
                "See Article 1 and Annex IV for details.",
                {"Article 1"},
                {"ANNEX IV"},
                {"Article 1": "Article 1 - Subject", "ANNEX IV": "ANNEX IV - List"},
                False,
                "See [[#Article 1 - Subject|Article 1]] and [[#ANNEX IV - List|Annex IV]] for details.",
            ),
            # Article reference inside parentheses
            (
                "(Article 1 applies)",
                {"Article 1"},
                set(),
                {"Article 1": "Article 1 - Subject"},
                False,
                "(Article 1 applies)",  # skipped because preceded by "("
            ),
            # Mixed known and unknown articles
            (
                "Article 1 and Article 99 apply.",
                {"Article 1"},
                set(),
                {"Article 1": "Article 1 - Subject"},
                False,
                "[[#Article 1 - Subject|Article 1]] and Article 99 apply.",
            ),
            # Article with number that is a prefix of another
            (
                "Article 1 and Article 10 apply.",
                {"Article 1", "Article 10"},
                set(),
                {"Article 1": "Article 1 - Subject", "Article 10": "Article 10 - Scope"},
                False,
                "[[#Article 1 - Subject|Article 1]] and [[#Article 10 - Scope|Article 10]] apply.",
            ),
            # Text with no references → unchanged
            (
                "No references here.",
                {"Article 1"},
                {"ANNEX IV"},
                {"Article 1": "Article 1 - Subject"},
                False,
                "No references here.",
            ),
            # Empty text → unchanged
            (
                "",
                {"Article 1"},
                set(),
                {},
                False,
                "",
            ),
            # Article reference followed by period
            (
                "See Article 1.",
                {"Article 1"},
                set(),
                {"Article 1": "Article 1 - Subject"},
                False,
                "See [[#Article 1 - Subject|Article 1]].",
            ),
            # Article reference followed by comma
            (
                "Under Article 1, the rules apply.",
                {"Article 1"},
                set(),
                {"Article 1": "Article 1 - Subject"},
                False,
                "Under [[#Article 1 - Subject|Article 1]], the rules apply.",
            ),
            # External reference with "of Directive"
            (
                "Article 1 of Directive 2014/24/EU",
                {"Article 1"},
                set(),
                {"Article 1": "Article 1 - Subject"},
                False,
                "Article 1 of Directive 2014/24/EU",
            ),
            # External reference with "of Decision"
            (
                "Annex IV of Decision 2024/123",
                set(),
                {"ANNEX IV"},
                {"ANNEX IV": "ANNEX IV - List"},
                False,
                "Annex IV of Decision 2024/123",
            ),
        ],
    )
    def test_resolve_edge_cases(
        self,
        input_text: str,
        article_ids: set[str],
        annex_ids: set[str],
        heading_map: dict[str, str],
        add_block_links: bool,
        expected: str,
    ) -> None:
        config = _make_config(links_style="wikilinks", add_block_links=add_block_links)
        result = _resolve_semantic_references(
            input_text,
            article_ids,
            annex_ids,
            config,
            heading_map=heading_map,
        )
        assert result == expected


# ---------------------------------------------------------------------------
# _resolve_semantic_references — Compound "Articles X and Y"
# ---------------------------------------------------------------------------


class TestResolveSemanticCompoundArticles:
    """Compound article reference resolution tests."""

    @pytest.mark.parametrize(
        "input_text, article_ids, heading_map, expected",
        [
            # Two articles with qualifiers → two separate block links
            (
                "Articles 5c(4) and 5e(2) apply.",
                {"Article 5c", "Article 5e"},
                {"Article 5c": "Article 5c - Penalties", "Article 5e": "Article 5e - Fines"},
                "Articles [[#^article-5c-4|5c(4)]] and [[#^article-5e-2|5e(2)]] apply.",
            ),
            # Two simple articles → heading links (label is just the number)
            (
                "Articles 1 and 3 set out the rules.",
                {"Article 1", "Article 3"},
                {"Article 1": "Article 1 - Subject", "Article 3": "Article 3 - Definitions"},
                "Articles [[#Article 1 - Subject|1]] and [[#Article 3 - Definitions|3]] set out the rules.",
            ),
            # Double qualifiers
            (
                "Articles 5a(1)(a) and 5b(2) require compliance.",
                {"Article 5a", "Article 5b"},
                {"Article 5a": "Article 5a - Scope", "Article 5b": "Article 5b - Obligations"},
                "Articles [[#^article-5a-1-a|5a(1)(a)]] and [[#^article-5b-2|5b(2)]] require compliance.",
            ),
            # Single article only (no "and" second)
            (
                "Articles 5c(4) establish the framework.",
                {"Article 5c"},
                {"Article 5c": "Article 5c - Penalties"},
                "Articles [[#^article-5c-4|5c(4)]] establish the framework.",
            ),
            # One known, one unknown → only known gets linked
            (
                "Articles 5c(4) and 99(1) apply.",
                {"Article 5c"},
                {"Article 5c": "Article 5c - Penalties"},
                "Articles [[#^article-5c-4|5c(4)]] and 99(1) apply.",
            ),
            # External reference → no linking
            (
                "Articles 5c(4) and 5e(2) of Regulation 2024/123",
                {"Article 5c", "Article 5e"},
                {"Article 5c": "Article 5c - Penalties", "Article 5e": "Article 5e - Fines"},
                "Articles 5c(4) and 5e(2) of Regulation 2024/123",
            ),
        ],
    )
    def test_compound_articles(
        self,
        input_text: str,
        article_ids: set[str],
        heading_map: dict[str, str],
        expected: str,
    ) -> None:
        config = _make_config(links_style="wikilinks", add_block_links=True)
        result = _resolve_semantic_references(
            input_text,
            article_ids,
            set(),
            config,
            heading_map=heading_map,
        )
        assert result == expected

    @pytest.mark.parametrize(
        "input_text, article_ids, heading_map, expected",
        [
            # Compound with markdown style
            (
                "Articles 5c(4) and 5e(2) apply.",
                {"Article 5c", "Article 5e"},
                {"Article 5c": "Article 5c - Penalties", "Article 5e": "Article 5e - Fines"},
                "Articles [5c(4)](#^article-5c-4) and [5e(2)](#^article-5e-2) apply.",
            ),
            # Compound without block links → heading links
            (
                "Articles 1 and 3 apply.",
                {"Article 1", "Article 3"},
                {"Article 1": "Article 1 - Subject", "Article 3": "Article 3 - Definitions"},
                "Articles [1](#Article%201%20-%20Subject) and [3](#Article%203%20-%20Definitions) apply.",
            ),
        ],
    )
    def test_compound_articles_markdown_style(
        self,
        input_text: str,
        article_ids: set[str],
        heading_map: dict[str, str],
        expected: str,
    ) -> None:
        config = _make_config(links_style="markdown", add_block_links=True)
        result = _resolve_semantic_references(
            input_text,
            article_ids,
            set(),
            config,
            heading_map=heading_map,
        )
        assert result == expected


# ---------------------------------------------------------------------------
# _resolve_semantic_references — Range "Articles X to Y" avoidance
# ---------------------------------------------------------------------------


class TestResolveSemanticRangeAvoidance:
    """Range construct avoidance: 'Articles X to Y' should NOT be linked."""

    @pytest.mark.parametrize(
        "input_text, article_ids, heading_map, expected",
        [
            # Simple range → preserved as plain text
            (
                "Articles 5 to 14 apply.",
                {
                    "Article 5",
                    "Article 6",
                    "Article 7",
                    "Article 8",
                    "Article 9",
                    "Article 10",
                    "Article 11",
                    "Article 12",
                    "Article 13",
                    "Article 14",
                },
                {"Article 5": "Article 5 - Subject"},
                "Articles 5 to 14 apply.",
            ),
            # Short range → preserved
            (
                "Articles 1 to 3 define the scope.",
                {"Article 1", "Article 2", "Article 3"},
                {"Article 1": "Article 1 - Subject", "Article 3": "Article 3 - Definitions"},
                "Articles 1 to 3 define the scope.",
            ),
            # Range with letter suffix → preserved
            (
                "Articles 5a to 5c are relevant.",
                {"Article 5a", "Article 5b", "Article 5c"},
                {"Article 5a": "Article 5a - Scope"},
                "Articles 5a to 5c are relevant.",
            ),
            # Range at end of sentence → preserved
            (
                "See Articles 10 to 20.",
                {"Article 10", "Article 20"},
                {"Article 10": "Article 10 - Scope"},
                "See Articles 10 to 20.",
            ),
            # Range followed by external reference → preserved
            (
                "Articles 1 to 5 of Regulation 2024/123",
                {"Article 1", "Article 5"},
                {"Article 1": "Article 1 - Subject"},
                "Articles 1 to 5 of Regulation 2024/123",
            ),
        ],
    )
    def test_range_not_linked(
        self,
        input_text: str,
        article_ids: set[str],
        heading_map: dict[str, str],
        expected: str,
    ) -> None:
        config = _make_config(links_style="wikilinks", add_block_links=True)
        result = _resolve_semantic_references(
            input_text,
            article_ids,
            set(),
            config,
            heading_map=heading_map,
        )
        assert result == expected

    def test_range_and_single_article_mixed(self) -> None:
        """Range preserved while standalone article reference is linked."""
        config = _make_config(links_style="wikilinks", add_block_links=True)
        result = _resolve_semantic_references(
            "Articles 5 to 14 apply. See also Article 1.",
            {"Article 1", "Article 5", "Article 14"},
            set(),
            config,
            heading_map={"Article 1": "Article 1 - Subject", "Article 5": "Article 5 - Scope"},
        )
        assert result == "Articles 5 to 14 apply. See also [[#Article 1 - Subject|Article 1]]."


# ---------------------------------------------------------------------------
# _resolve_semantic_references — External reference edge cases
# ---------------------------------------------------------------------------

class TestResolveSemanticExternalEdgeCases:
    """External document reference patterns that should NOT be linked."""

    @pytest.mark.parametrize(
        "input_text, article_ids, annex_ids, heading_map, expected",
        [
            # ", of Directive" — comma before "of"
            (
                "Article 2 point (1), of Directive (EU) 2016/943",
                {"Article 2"},
                set(),
                {"Article 2": "Article 2 - Requirements"},
                "Article 2 point (1), of Directive (EU) 2016/943",
            ),
            # " to Implementing Regulation" — annex-style external ref
            (
                "Annex I to Implementing Regulation (EU) 2015/1502",
                set(),
                {"ANNEX I"},
                {"ANNEX I": "ANNEX I - List"},
                "Annex I to Implementing Regulation (EU) 2015/1502",
            ),
            # " of the Commission" — article "the" between "of" and keyword
            (
                "Annex I of the Commission Implementing Regulation (EU) 2024/482",
                set(),
                {"ANNEX I"},
                {"ANNEX I": "ANNEX I - List"},
                "Annex I of the Commission Implementing Regulation (EU) 2024/482",
            ),
            # " of the Council Directive" — article "the" before keyword
            (
                "Article 5 of the Council Directive 2014/53/EU",
                {"Article 5"},
                set(),
                {"Article 5": "Article 5 - Scope"},
                "Article 5 of the Council Directive 2014/53/EU",
            ),
            # " to the Delegated Regulation" — article "the" in "to" variant
            (
                "Annex II to the Delegated Regulation 2024/123",
                set(),
                {"ANNEX II"},
                {"ANNEX II": "ANNEX II - Criteria"},
                "Annex II to the Delegated Regulation 2024/123",
            ),
        ],
    )
    def test_external_ref_edge_cases(
        self,
        input_text: str,
        article_ids: set[str],
        annex_ids: set[str],
        heading_map: dict[str, str],
        expected: str,
    ) -> None:
        config = _make_config(links_style="wikilinks", add_block_links=True)
        result = _resolve_semantic_references(
            input_text, article_ids, annex_ids, config, heading_map=heading_map,
        )
        assert result == expected


# ---------------------------------------------------------------------------
# _resolve_semantic_references — Article with paren + point qualifier
# ---------------------------------------------------------------------------

class TestResolveSemanticParenPointQualifier:
    """Article references with both parenthesized qualifier AND ', point (x)'."""

    @pytest.mark.parametrize(
        "input_text, article_ids, heading_map, expected",
        [
            # "(3), point (b)" → block link with both parts
            (
                "Article 3(3), point (b) are fulfilled",
                {"Article 3"},
                {"Article 3": "Article 3 - Definitions"},
                "[[#^article-3-3-b|Article 3(3), point (b)]] are fulfilled",
            ),
            # "(1), point (a)" → block link
            (
                "Under Article 1(1), point (a) the rules apply.",
                {"Article 1"},
                {"Article 1": "Article 1 - Subject"},
                "Under [[#^article-1-1-a|Article 1(1), point (a)]] the rules apply.",
            ),
            # "(2)(a), point (i)" → deep block link
            (
                "Article 5(2)(a), point (i) specifies",
                {"Article 5"},
                {"Article 5": "Article 5 - Obligations"},
                "[[#^article-5-2-a-i|Article 5(2)(a), point (i)]] specifies",
            ),
            # "point (1)" standalone (no paren prefix) → block link
            (
                "Article 2 point (1) defines the terms.",
                {"Article 2"},
                {"Article 2": "Article 2 - Definitions"},
                "[[#^article-2-1|Article 2 point (1)]] defines the terms.",
            ),
        ],
    )
    def test_paren_point_qualifier(
        self, input_text: str, article_ids: set[str], heading_map: dict[str, str], expected: str,
    ) -> None:
        config = _make_config(links_style="wikilinks", add_block_links=True)
        result = _resolve_semantic_references(
            input_text, article_ids, set(), config, heading_map=heading_map,
        )
        assert result == expected


# ---------------------------------------------------------------------------
# _resolve_semantic_references — Comma-separated article lists
# ---------------------------------------------------------------------------

class TestResolveSemanticCommaSeparatedArticles:
    """Comma-separated article lists like 'Articles 7, 9, 10, 12 and 12a'."""

    @pytest.mark.parametrize(
        "input_text, article_ids, heading_map, expected",
        [
            # Full comma-separated list with "and" before last
            (
                "Articles 7, 9, 10, 12 and 12a apply.",
                {"Article 7", "Article 9", "Article 10", "Article 12", "Article 12a"},
                {
                    "Article 7": "Article 7", "Article 9": "Article 9",
                    "Article 10": "Article 10", "Article 12": "Article 12",
                    "Article 12a": "Article 12a",
                },
                "Articles [[#Article 7|7]], [[#Article 9|9]], [[#Article 10|10]], [[#Article 12|12]] and [[#Article 12a|12a]] apply.",
            ),
            # Simple two-article list
            (
                "Articles 1 and 3 set out the rules.",
                {"Article 1", "Article 3"},
                {"Article 1": "Article 1 - Subject", "Article 3": "Article 3 - Definitions"},
                "Articles [[#Article 1 - Subject|1]] and [[#Article 3 - Definitions|3]] set out the rules.",
            ),
            # Three-article list
            (
                "Articles 5, 6 and 7 define the scope.",
                {"Article 5", "Article 6", "Article 7"},
                {"Article 5": "Article 5 - Scope", "Article 6": "Article 6 - Obligations", "Article 7": "Article 7 - Penalties"},
                "Articles [[#Article 5 - Scope|5]], [[#Article 6 - Obligations|6]] and [[#Article 7 - Penalties|7]] define the scope.",
            ),
            # With qualifiers in list
            (
                "Articles 5c(4), 5e(2) and 5f apply.",
                {"Article 5c", "Article 5e", "Article 5f"},
                {"Article 5c": "Article 5c - Penalties", "Article 5e": "Article 5e - Fines", "Article 5f": "Article 5f - Review"},
                "Articles [[#^article-5c-4|5c(4)]], [[#^article-5e-2|5e(2)]] and [[#Article 5f - Review|5f]] apply.",
            ),
            # Some known, some unknown in list
            (
                "Articles 7, 99 and 10 apply.",
                {"Article 7", "Article 10"},
                {"Article 7": "Article 7", "Article 10": "Article 10"},
                "Articles [[#Article 7|7]], 99 and [[#Article 10|10]] apply.",
            ),
            # External reference → no linking
            (
                "Articles 1, 2 and 3 of Regulation (EU) 2016/679",
                {"Article 1", "Article 2", "Article 3"},
                {"Article 1": "Article 1 - Subject"},
                "Articles 1, 2 and 3 of Regulation (EU) 2016/679",
            ),
        ],
    )
    def test_comma_separated_articles(
        self, input_text: str, article_ids: set[str], heading_map: dict[str, str], expected: str,
    ) -> None:
        config = _make_config(links_style="wikilinks", add_block_links=True)
        result = _resolve_semantic_references(
            input_text, article_ids, set(), config, heading_map=heading_map,
        )
        assert result == expected


# ---------------------------------------------------------------------------
# _resolve_semantic_references — Additional external reference edge cases
# ---------------------------------------------------------------------------

class TestResolveSemanticExternalMoreEdgeCases:
    """More external document reference patterns that should NOT be linked."""

    @pytest.mark.parametrize(
        "input_text, article_ids, annex_ids, heading_map, expected",
        [
            # ", point (1), of Regulation" — qualifier then comma then external
            (
                "Article 4, point (1), of Regulation (EU) 2016/679",
                {"Article 4"},
                set(),
                {"Article 4": "Article 4 - Scope"},
                "Article 4, point (1), of Regulation (EU) 2016/679",
            ),
            # "of that Directive" — demonstrative pronoun
            (
                "Article 21 of that Directive",
                {"Article 21"},
                set(),
                {"Article 21": "Article 21 - Scope"},
                "Article 21 of that Directive",
            ),
            # "of that Regulation" — demonstrative pronoun
            (
                "Article 5 of that Regulation",
                {"Article 5"},
                set(),
                {"Article 5": "Article 5 - Obligations"},
                "Article 5 of that Regulation",
            ),
            # ", point (46), identified" — point qualifier followed by non-external text
            (
                "in Article 3, point (46), identified",
                {"Article 3"},
                set(),
                {"Article 3": "Article 3 - Definitions"},
                "in [[#^article-3-46|Article 3, point (46)]], identified",
            ),
        ],
    )
    def test_external_more_edge_cases(
        self,
        input_text: str,
        article_ids: set[str],
        annex_ids: set[str],
        heading_map: dict[str, str],
        expected: str,
    ) -> None:
        config = _make_config(links_style="wikilinks", add_block_links=True)
        result = _resolve_semantic_references(
            input_text, article_ids, annex_ids, config, heading_map=heading_map,
        )
        assert result == expected


# ---------------------------------------------------------------------------
# Template: Add your own test cases here
# ---------------------------------------------------------------------------
# To add new test cases, simply append tuples to the parametrize lists below.
# Format: (input_text, expected_output)
#
# For article tests you also need:
#   - article_ids: set of known article IDs (e.g. {"Article 1", "Article 5a"})
#   - heading_map: dict mapping article ID → full heading label
#
# For annex tests you also need:
#   - annex_ids: set of known annex IDs (e.g. {"ANNEX IV", "ANNEX I"})
#   - heading_map: dict mapping annex ID → full heading label
#
# Example:
#   ("Article 2(3) says", {"Article 2"}, {"Article 2": "Article 2 - Rules"}, "[[^article-2-3|Article 2(3)]] says"),
# ---------------------------------------------------------------------------


class TestSemanticLinkTemplate:
    """Template class for adding custom semantic link resolution test cases.

    Add your own parametrized test cases below. Each case is simply:
      input_text → expected_output

    For article tests you also need:
      - article_ids: set of known article IDs (e.g. {"Article 1", "Article 5a"})
      - heading_map: dict mapping article ID → full heading label

    For annex tests you also need:
      - annex_ids: set of known annex IDs (e.g. {"ANNEX IV", "ANNEX I"})
      - heading_map: dict mapping annex ID → full heading label

    Example:
        ("Article 2(3) says", {"Article 2"}, {"Article 2": "Full Heading"}, "[[#^article-2-3|Article 2(3)]] says"),
    """

    @pytest.mark.parametrize(
        "input_text, article_ids, heading_map, expected",
        [
            # --- Add your article test cases here ---
            # ("input text", {"Article X"}, {"Article X": "Full Heading"}, "expected output"),
        ],
    )
    def test_custom_article_cases(
        self,
        input_text: str,
        article_ids: set[str],
        heading_map: dict[str, str],
        expected: str,
    ) -> None:
        config = _make_config(links_style="wikilinks", add_block_links=True)
        result = _resolve_semantic_references(
            input_text,
            article_ids,
            set(),
            config,
            heading_map=heading_map,
        )
        assert result == expected

    @pytest.mark.parametrize(
        "input_text, annex_ids, heading_map, expected",
        [
            # --- Add your annex test cases here ---
            # ("input text", {"ANNEX X"}, {"ANNEX X": "Full Heading"}, "expected output"),
        ],
    )
    def test_custom_annex_cases(
        self,
        input_text: str,
        annex_ids: set[str],
        heading_map: dict[str, str],
        expected: str,
    ) -> None:
        config = _make_config(links_style="wikilinks", add_block_links=True)
        result = _resolve_semantic_references(
            input_text,
            set(),
            annex_ids,
            config,
            heading_map=heading_map,
        )
        assert result == expected

    @pytest.mark.parametrize(
        "input_text, article_ids, annex_ids, heading_map, expected",
        [
            # --- Add your combined/mixed test cases here ---
            # ("input text", {"Article X"}, {"ANNEX Y"}, {"...": "..."}, "expected output"),
        ],
    )
    def test_custom_combined_cases(
        self,
        input_text: str,
        article_ids: set[str],
        annex_ids: set[str],
        heading_map: dict[str, str],
        expected: str,
    ) -> None:
        config = _make_config(links_style="wikilinks", add_block_links=True)
        result = _resolve_semantic_references(
            input_text,
            article_ids,
            annex_ids,
            config,
            heading_map=heading_map,
        )
        assert result == expected
