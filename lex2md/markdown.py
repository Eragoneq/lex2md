from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

from lex2md.models import EurLexDocument, Note, Paragraph, Point, Recital, Section


@dataclass
class RenderConfig:
    links_style: str = "markdown"
    add_block_links: bool = False
    resolve_semantic_links: bool = False


def generate_markdown(
    document: EurLexDocument | dict,
    *,
    links_style: str = "markdown",
    add_block_links: bool = False,
    resolve_semantic_links: bool = False,
) -> str:
    config = RenderConfig(
        links_style=links_style,
        add_block_links=add_block_links,
        resolve_semantic_links=resolve_semantic_links,
    )
    parsed = _coerce_document(document)
    # Map section IDs to their full heading labels for wikilink targets
    article_ids: set[str] = {section.id for section in parsed.articles if section.id}
    annex_ids: set[str] = {section.id for section in parsed.annexes if section.id}
    heading_map: dict[str, str] = {}
    for section in parsed.articles:
        if section.id:
            heading_map[section.id] = _section_header(section)
    for section in parsed.annexes:
        if section.id:
            heading_map[section.id] = _section_header(section)
    link_ctx = _LinkContext(article_ids, annex_ids, heading_map, config)

    parts: list[str] = []

    if parsed.title:
        parts.append(f"# {parsed.title}")
        parts.append("")

    if parsed.celex:
        parts.append(f"- CELEX: `{parsed.celex}`")
        parts.append(f"- Language: `{parsed.language}`")
        parts.append("")

    nav_lines = _build_navigation(parsed, config)
    if nav_lines:
        parts.extend(nav_lines)
        parts.append("")

    if parsed.preamble:
        parts.append("## Preamble")
        parts.append("")
        preamble_text = parsed.preamble
        if config.add_block_links:
            preamble_text = _namespace_footnote_refs(preamble_text)
        preamble_text = _apply_intra_links(preamble_text, link_ctx)
        parts.append(preamble_text)
        notes = _format_notes(parsed.preamble_notes, config)
        if notes:
            parts.append("")
            parts.append(notes)
        parts.append("")

    if parsed.articles:
        parts.append("## Articles")
        parts.append("")
        has_grouping = any(
            article.chapter_id
            or article.chapter_title
            or article.section_id
            or article.section_title
            for article in parsed.articles
        )
        article_heading_level = 4 if has_grouping else 3
        current_chapter: tuple[str, str] = ("", "")
        current_section: tuple[str, str] = ("", "")

        for article in parsed.articles:
            chapter = (article.chapter_id, article.chapter_title)
            section = (article.section_id, article.section_title)

            if chapter != ("", "") and chapter != current_chapter:
                parts.append(_render_group_heading(*chapter, label="Chapter", level=3))
                parts.append("")
                current_chapter = chapter
                current_section = ("", "")

            if section != ("", "") and section != current_section:
                parts.append(_render_group_heading(*section, label="Section", level=4))
                parts.append("")
                current_section = section

            parts.extend(
                _render_section(
                    article, heading_level=article_heading_level, config=config, link_ctx=link_ctx
                )
            )

    if parsed.final_text or parsed.signature_lines:
        parts.append("## Final Provisions")
        parts.append("")
        if parsed.final_text:
            parts.append(parsed.final_text)
        if parsed.signature_lines:
            if parsed.final_text:
                parts.append("")
            parts.extend(f"- {line}" for line in parsed.signature_lines)
        parts.append("")

    if parsed.annexes:
        parts.append("## Annexes")
        parts.append("")
        has_grouping = any(
            annex.chapter_id or annex.chapter_title or annex.section_id or annex.section_title
            for annex in parsed.annexes
        )
        annex_heading_level = 4 if has_grouping else 3
        current_chapter: tuple[str, str] = ("", "")
        current_section: tuple[str, str] = ("", "")

        for annex in parsed.annexes:
            chapter = (annex.chapter_id, annex.chapter_title)
            section = (annex.section_id, annex.section_title)

            if chapter != ("", "") and chapter != current_chapter:
                parts.append(_render_group_heading(*chapter, label="Chapter", level=3))
                parts.append("")
                current_chapter = chapter
                current_section = ("", "")

            if section != ("", "") and section != current_section:
                parts.append(_render_group_heading(*section, label="Section", level=4))
                parts.append("")
                current_section = section

            parts.extend(
                _render_section(
                    annex, heading_level=annex_heading_level, config=config, link_ctx=link_ctx
                )
            )

    return "\n".join(parts).strip()


@dataclass
class _LinkContext:
    """Carries known section IDs and heading labels through the render pipeline."""

    article_ids: set[str]
    annex_ids: set[str]
    heading_map: dict[str, str]  # section.id → full heading label
    config: RenderConfig


def _render_section(
    section: Section,
    *,
    heading_level: int,
    config: RenderConfig,
    link_ctx: _LinkContext | None = None,
) -> list[str]:
    level = "#" * heading_level
    header = _section_header(section)

    # Headings never get block links — Obsidian natively references headings.
    header_line = f"{level} {header}"
    lines = [header_line]
    lines.append("")

    section_content = _render_section_content(section, config, link_ctx)
    if section_content:
        lines.extend(section_content)

    notes = _format_notes(section.notes, config)
    if notes:
        lines.append("")
        lines.append(notes)

    lines.append("")
    return lines


def _section_header(section: Section) -> str:
    parts = [part for part in [section.id, section.title] if part]
    return " - ".join(parts) if parts else "Section"


def _render_group_heading(group_id: str, group_title: str, *, label: str, level: int) -> str:
    heading = group_id.strip()
    title = group_title.strip()
    if heading and title:
        content = f"{heading} - {title}"
    else:
        content = heading or title or label
    return f"{'#' * level} {content}"


def _format_notes(notes: list[Note], config: RenderConfig) -> str:
    """Format footnotes.

    When block links are active we namespace footnote IDs with ``fn-`` so that
    the ``[^id]`` / ``[^fn-id]`` syntax never collides with Obsidian block-link
    ``^id`` identifiers.
    """
    if not notes:
        return ""
    lines = ["---", ""]
    for note in notes:
        note_id = f"fn-{note.id}" if config.add_block_links else note.id
        lines.append(f"[^{note_id}]: {note.text}")
    return "\n".join(lines)


def _render_section_content(
    section: Section, config: RenderConfig, link_ctx: _LinkContext | None = None
) -> list[str]:
    base_id = _slugify(section.id) if section.id else "section"
    if section.paragraphs:
        return _render_paragraphs(section.paragraphs, base_id, config, link_ctx)
    if section.body:
        body = section.body
        if config.add_block_links:
            body = _namespace_footnote_refs(body)
        if link_ctx:
            body = _apply_intra_links(body, link_ctx)
        return [body]
    return []


def _render_paragraphs(
    paragraphs: list[Paragraph],
    base_id: str,
    config: RenderConfig,
    link_ctx: _LinkContext | None = None,
) -> list[str]:
    lines: list[str] = []
    total = len(paragraphs)
    for index, paragraph in enumerate(paragraphs):
        prefix = f"{paragraph.number}." if paragraph.number else ""
        text = paragraph.text.strip()
        if config.add_block_links:
            text = _namespace_footnote_refs(text)
        if link_ctx:
            text = _apply_intra_links(text, link_ctx)

        p_idx = paragraph.number.lower() if paragraph.number else f"p{index}"
        block_id = f"{base_id}-{p_idx}"

        main_line = f"{prefix} {text}".strip()
        if config.add_block_links:
            main_line += f" ^{block_id}"

        lines.append(main_line)
        
        point_indent = 3 if paragraph.number else 0
        point_parent_id = block_id if paragraph.number else base_id
        lines.extend(_render_paragraph_points(paragraph.points, point_parent_id, config, point_indent, link_ctx))
        if index + 1 < total:
            lines.append("")
    return lines


def _render_paragraph_points(
    points: list[Point],
    parent_id: str,
    config: RenderConfig,
    indent: int,
    link_ctx: _LinkContext | None = None,
) -> list[str]:
    filtered = [point for point in points if point.text.strip()]
    if not filtered:
        return []

    lines: list[str] = []
    for index, point in enumerate(filtered):
        marker_slug = (
            re.sub(r"[^a-zA-Z0-9]", "", point.marker.lower()) if point.marker else f"pt{index}"
        )
        pt_id = f"{parent_id}-{marker_slug}"
        lines.extend(
            _render_point_with_nested_dash_list(point, pt_id, config, indent=indent, link_ctx=link_ctx)
        )
    return lines


def _render_point_with_nested_dash_list(
    point: Point,
    block_id: str,
    config: RenderConfig,
    *,
    indent: int,
    link_ctx: _LinkContext | None = None,
) -> list[str]:
    lead_text, nested_items = _split_inline_dash_items(point.text)
    if config.add_block_links:
        lead_text = _namespace_footnote_refs(lead_text)
    if link_ctx:
        lead_text = _apply_intra_links(lead_text, link_ctx)

    main_line = f"{' ' * indent}- {_format_point_text(point.marker, lead_text)}".rstrip()
    if config.add_block_links:
        main_line += f" ^{block_id}"
    lines = [main_line]

    if point.subpoints:
        lines.extend(
            _render_point_subpoints(
                point.subpoints, block_id, config, indent=indent + 3, link_ctx=link_ctx
            )
        )

    lines.extend(
        _render_nested_dash_items(
            nested_items, block_id, config, indent=indent + 3, link_ctx=link_ctx
        )
    )
    return lines


def _render_point_subpoints(
    subpoints: list[Point],
    parent_id: str,
    config: RenderConfig,
    *,
    indent: int,
    link_ctx: _LinkContext | None = None,
) -> list[str]:
    lines: list[str] = []
    for index, subpoint in enumerate(subpoints):
        marker_slug = (
            re.sub(r"[^a-zA-Z0-9]", "", subpoint.marker.lower())
            if subpoint.marker
            else f"spt{index}"
        )
        spt_id = f"{parent_id}-{marker_slug}"
        lines.extend(
            _render_point_with_nested_dash_list(
                subpoint, spt_id, config, indent=indent, link_ctx=link_ctx
            )
        )
    return lines


def _render_nested_dash_items(
    items: list[str],
    parent_id: str,
    config: RenderConfig,
    *,
    indent: int,
    link_ctx: _LinkContext | None = None,
) -> list[str]:
    lines: list[str] = []
    for index, item in enumerate(items):
        item_id = f"{parent_id}-d{index}"
        lead_text, children = _split_inline_dash_items(item)
        item_text = lead_text.strip() if children else item.strip()
        if config.add_block_links:
            item_text = _namespace_footnote_refs(item_text)
        if link_ctx:
            item_text = _apply_intra_links(item_text, link_ctx)

        child_indent = indent
        if item_text:
            line = f"{' ' * indent}- {item_text}"
            if config.add_block_links:
                line += f" ^{item_id}"
            lines.append(line)
            child_indent = indent + 3

        if children:
            lines.extend(
                _render_nested_dash_items(
                    children, item_id, config, indent=child_indent, link_ctx=link_ctx
                )
            )

    return lines


def _namespace_footnote_refs(text: str) -> str:
    """Rewrite ``[^id]`` inline footnote references to ``[^fn-id]`` so they
    don't clash with Obsidian block-link ``^id`` anchors."""
    return re.sub(r"\[\^([^\]]+)\]", r"[^fn-\1]", text)


def _format_point_text(marker: str, text: str) -> str:
    marker_text = marker.strip()
    body_text = text.strip()
    if marker_text in {"-", "—"}:
        return body_text
    return f"{marker_text} {body_text}".strip()


def _split_inline_dash_items(text: str) -> tuple[str, list[str]]:
    cleaned = text.strip()
    if not cleaned:
        return "", []

    start_match = _find_first_dash_marker(cleaned, allowed_delimiters={"^", "\n", ":"})
    if not start_match:
        return cleaned, []

    start_position, _, _ = start_match
    lead = cleaned[:start_position].rstrip()
    items = _split_dash_list_items(cleaned[start_position:])

    if not items:
        return cleaned, []
    return lead, items


def _split_dash_list_items(text: str) -> list[str]:
    markers = _find_dash_markers(text, allowed_delimiters={"^", "\n", ";", ".", ":"})
    if not markers:
        return []

    items: list[str] = []
    current = 0
    nested_active = False

    for index in range(1, len(markers)):
        next_start, _, delimiter = markers[index]

        if delimiter == ":":
            nested_active = True
            continue

        if delimiter == ";" and nested_active:
            continue

        if delimiter not in {";", "\n", "."}:
            continue

        chunk = text[markers[current][1] : next_start].strip().rstrip(";").strip()
        if chunk:
            items.append(chunk)

        current = index
        nested_active = False

    chunk = text[markers[current][1] :].strip().rstrip(";").strip()
    if chunk:
        items.append(chunk)

    return items


def _find_first_dash_marker(
    text: str, *, allowed_delimiters: set[str]
) -> tuple[int, int, str] | None:
    markers = _find_dash_markers(text, allowed_delimiters=allowed_delimiters)
    return markers[0] if markers else None


def _find_dash_markers(text: str, *, allowed_delimiters: set[str]) -> list[tuple[int, int, str]]:
    markers: list[tuple[int, int, str]] = []
    for match in re.finditer(r"[—-]\s+", text):
        delimiter = _dash_delimiter_before(text, match.start())
        if delimiter in allowed_delimiters:
            markers.append((match.start(), match.end(), delimiter))
    return markers


def _dash_delimiter_before(text: str, start: int) -> str:
    index = start - 1
    while index >= 0 and text[index] in {" ", "\t", "\r"}:
        index -= 1
    if index < 0:
        return "^"
    return "\n" if text[index] == "\n" else text[index]


def _coerce_document(document: EurLexDocument | dict) -> EurLexDocument:
    if isinstance(document, EurLexDocument):
        return document

    preamble_recitals = [Recital(**recital) for recital in document.get("preamble_recitals", [])]
    preamble_notes = [Note(**note) for note in document.get("preamble_notes", [])]
    articles = [_dict_to_section(item) for item in document.get("articles", [])]
    annexes = [_dict_to_section(item) for item in document.get("annexes", [])]

    return EurLexDocument(
        title=document.get("title", ""),
        preamble=document.get("preamble", ""),
        preamble_intro=document.get("preamble_intro", ""),
        preamble_recitals=preamble_recitals,
        preamble_notes=preamble_notes,
        articles=articles,
        final_text=document.get("final_text", ""),
        signature_lines=document.get("signature_lines", []),
        annexes=annexes,
        celex=document.get("celex", ""),
        language=document.get("language", "en"),
    )


def _build_navigation(document: EurLexDocument, config: RenderConfig) -> list[str]:
    # Navigation only makes sense with wikilinks — standard markdown anchor links
    # require <a id="..."> tags which we no longer emit.
    if config.links_style != "wikilinks":
        return []

    lines: list[str] = []
    entries: list[str] = []

    for section in document.articles:
        entries.append(_section_header(section))
    for section in document.annexes:
        entries.append(_section_header(section))

    if not entries:
        return lines

    lines.append("## Navigation")
    lines.append("")
    for label in entries:
        lines.append(f"- [[#{label}]]")
    return lines


# ---------------------------------------------------------------------------
# Semantic link resolution
# ---------------------------------------------------------------------------

# Matches text after a reference that indicates an external document.
# Handles:
#   " of Regulation..." / " of Directive..." / " of Decision..."
#   ", of Directive..." (comma before "of")
#   " of the Commission..." / " of the Council..." (optional article "the")
#   " of that Directive..." / " of that Regulation..." (demonstrative "that")
#   " to Implementing Regulation..." (annex-style external refs)
_EXTERNAL_DOC_SUFFIX = (
    r"(?:[,\s]+of\s+(?:the\s+|that\s+)?"
    r"(?:Regulation|Directive|Decision|Delegated|Implementing|Commission|Council|European)\b)"
    r"|(?:\s+to\s+(?:the\s+|that\s+)?"
    r"(?:Regulation|Directive|Decision|Delegated|Implementing|Commission|Council|European)\b)"
)

# Pattern for a single article-like reference with optional inline qualifiers.
# Captures:
#   group "base"  – e.g. "Article 5a"
#   group "qual"  – e.g. "(4)" or "(1)(a)" or " paragraph 5, point (a)" or "(3), point (b)"
#
# Negative lookbehind (?<!s) prevents matching "Article 5" inside "Articles 5".
# Negative lookahead (?! … to \d) skips range constructs like "Articles 5 to 14".
_ARTICLE_REF = (
    r"(?<!s)(?P<base>Article\s+\d+[a-zA-Z]?)"
    r"(?P<qual>"
    r"(?:\s+paragraph\s+\d+(?:,?\s+point\s+\(?[a-zA-Z0-9]+\)?)?)"  # paragraph N, point (x) style
    r"|(?:\(\s*[a-zA-Z0-9]+\s*\))+(?:,?\s+point\s+\(?[a-zA-Z0-9]+\s*\)?)"  # (1)(a), point (b) style
    r"|(?:\(\s*[a-zA-Z0-9]+\s*\))+"  # (1)(a) style
    r"|(?:\s+point\s+\(?[a-zA-Z0-9]+\s*\)?)"  # point (1) style (standalone, no paragraph)
    r"|(?:,\s*point\s+\(?[a-zA-Z0-9]+\s*\)?)"  # , point (46) style (comma before point)
    r")?"
    r"(?!\s+to\s+\d)"  # skip "Article 5 to 14" range references
)

# Pattern for compound "Articles X, Y, Z and W" references.
# Must be applied BEFORE _ARTICLE_REF so the longer match wins.
# Handles:
#   "Articles 5c(4) and 5e(2)" – two articles with qualifiers
#   "Articles 7, 9, 10, 12 and 12a" – comma-separated list
#   "Articles 5c(4)" – single article under "Articles" heading
# Negative lookahead skips range constructs like "Articles 5 to 14".
_ARTICLES_COMPOUND = (
    r"Articles\s+"
    r"(?P<items>"
    r"\d+[a-zA-Z]?(?:\(\s*[a-zA-Z0-9]+\s*\))*"  # first article number + optional qualifiers
    r"(?:"
    r",\s*\d+[a-zA-Z]?(?:\(\s*[a-zA-Z0-9]+\s*\))*"  # comma-separated: , 9, , 10
    r")*"
    r"(?:\s+and\s+\d+[a-zA-Z]?(?:\(\s*[a-zA-Z0-9]+\s*\))*)?"  # optional final: and 12a
    r")"
    r"(?!\s+to\s+\d)"  # skip range: "Articles 5 to 14"
)

# Pattern for annex references with optional ", point N"
_ANNEX_REF = (
    r"(?P<annex_base>(?:ANNEX|Annex)\s+[IVXLCDM]+(?:\s+[A-Z])?)"
    r"(?P<annex_qual>"
    r"(?:,?\s+point\s+\(?\s*[a-zA-Z0-9]+\s*\)?)"  # , point (1) or , point 1
    r"|(?:(?:\(\s*[a-zA-Z0-9]+\s*\))+)"  # (1)(a) style
    r")?"
)


def _is_external_reference(source: str, match_end: int) -> bool:
    """Check if text after the match indicates an external document reference.

    Searches the remainder for external doc patterns anywhere (not just at the
    start), so constructs like ``Article 4, point (1), of Regulation`` are
    correctly identified as external.
    """
    remainder = source[match_end:]
    return bool(re.search(_EXTERNAL_DOC_SUFFIX, remainder))


def _build_case_insensitive_id_set(
    ids: set[str],
) -> set[str]:
    """Build a set that contains both original and case variants."""
    result: set[str] = set()
    for key in ids:
        result.add(key)
        result.add(key.upper())
        result.add(key.title())
        # Handle "Annex IV" / "ANNEX IV" specifically
        if key.upper().startswith("ANNEX"):
            result.add("Annex" + key[5:])
            result.add("ANNEX" + key[5:])
    return result


def _build_case_insensitive_heading_map(
    heading_map: dict[str, str],
) -> dict[str, str]:
    """Build a heading map that also contains case variants of annex IDs."""
    result: dict[str, str] = dict(heading_map)
    for key, heading in heading_map.items():
        result[key.upper()] = heading
        result[key.title()] = heading
        if key.upper().startswith("ANNEX"):
            result["Annex" + key[5:]] = heading
            result["ANNEX" + key[5:]] = heading
    return result


def _resolve_semantic_references(
    text: str,
    article_ids: set[str],
    annex_ids: set[str],
    config: RenderConfig,
    heading_map: dict[str, str] | None = None,
) -> str:
    """Post-process text to resolve human-readable citations into internal links.

    Handles patterns like:
    - "Article 3"  →  wikilink to heading
    - "Article 3(1)(a)"  →  block link ^article-3-1-a
    - "Article 3 paragraph 5, point (a)"  →  block link ^article-3-5-a
    - "Articles 5c(4) and 5e(2)"  →  two separate links
    - "Annex IV"  →  wikilink to heading
    - "Annex IV, point 1"  →  block link ^annex-iv-1
    - Skips references followed by "of Regulation..." (external doc)
    """
    result = text
    expanded_annex_ids = _build_case_insensitive_id_set(annex_ids)
    expanded_heading_map = _build_case_insensitive_heading_map(heading_map or {})

    # 1. Handle compound "Articles X and Y" first (longer match)
    result = re.sub(
        _ARTICLES_COMPOUND,
        lambda m: _replace_compound_articles(m, article_ids, config, expanded_heading_map),
        result,
    )

    # 2. Handle single "Article X" references (skip already-linked ones)
    result = re.sub(
        _ARTICLE_REF,
        lambda m: _replace_single_article(m, article_ids, config, expanded_heading_map),
        result,
    )

    # 3. Handle annex references
    result = re.sub(
        _ANNEX_REF,
        lambda m: _replace_annex_ref(m, expanded_annex_ids, config, expanded_heading_map),
        result,
    )

    return result


def _replace_compound_articles(
    match: re.Match[str],
    known_ids: set[str],
    config: RenderConfig,
    heading_map: dict[str, str] | None = None,
) -> str:
    """Replace 'Articles 5c(4) and 5e(2)' or 'Articles 7, 9, 10 and 12a' with
    individual links.

    Skips range constructs like 'Articles 5 to 14' — those are not converted.
    Skips external references like 'Articles 1 to 5 of Regulation...'.
    """
    full = match.group(0)
    start = match.start()
    source = match.string
    if start > 0 and source[start - 1] in {"[", "|"}:
        return full
    if _is_external_reference(source, match.end()):
        return full

    # Skip range constructs: "Articles 5 to 14"
    remainder = source[match.end():]
    if re.match(r"\s+to\s+\d", remainder):
        return full

    items_raw = match.group("items")
    # Split by comma and/or "and" to get individual article tokens
    tokens = re.split(r",\s*|\s+and\s+", items_raw)

    linked: list[str] = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        link = _linkify_article_token(token, known_ids, config, heading_map)
        linked.append(link)

    if not linked:
        return full

    # Reconstruct: "Articles" + linked tokens joined with ", " and " and "
    if len(linked) == 1:
        return f"Articles {linked[0]}"
    if len(linked) == 2:
        return f"Articles {linked[0]} and {linked[1]}"
    return f"Articles {', '.join(linked[:-1])} and {linked[-1]}"


def _replace_single_article(
    match: re.Match[str],
    known_ids: set[str],
    config: RenderConfig,
    heading_map: dict[str, str] | None = None,
) -> str:
    """Replace 'Article 5a(23)' or 'Article 3 paragraph 5, point (a)' with a link."""
    full = match.group(0)
    start = match.start()
    source = match.string
    if start > 0 and source[start - 1] in {"[", "|", "("}:
        return full
    if _is_external_reference(source, match.end()):
        return full
    # Skip if this is part of the already-handled "Articles" compound.
    prefix_start = max(0, start - 9)
    before = source[prefix_start:start]
    if re.search(r"Articles\s*$", before):
        return full
    # Skip if already inside a wikilink or markdown link (e.g. [[#Article 1 - Subject|1]]).
    if "[[" in before or "](" in before:
        return full

    base = match.group("base")  # "Article 5a"
    qual = match.group("qual") or ""

    if base not in known_ids:
        return full

    slug = _slugify(base)
    heading = (heading_map or {}).get(base, base)
    target = heading  # full heading label
    if qual.strip() and config.add_block_links:
        parts = _extract_qualifier_parts(qual)
        if parts:
            target = f"^{slug}-{'-'.join(parts)}"

    return _format_link(full, target, config.links_style)


def _replace_annex_ref(
    match: re.Match[str],
    known_ids: set[str],
    config: RenderConfig,
    heading_map: dict[str, str] | None = None,
) -> str:
    """Replace 'Annex IV' or 'Annex IV, point 1' with a link."""
    full = match.group(0)
    start = match.start()
    source = match.string
    if start > 0 and source[start - 1] in {"[", "|"}:
        return full
    if _is_external_reference(source, match.end()):
        return full

    annex_base = match.group("annex_base")
    annex_qual = match.group("annex_qual") or ""

    if annex_base not in known_ids:
        return full

    slug = _slugify(annex_base)
    heading = (heading_map or {}).get(annex_base, annex_base)
    target = heading  # full heading label
    if annex_qual.strip() and config.add_block_links:
        parts = _extract_qualifier_parts(annex_qual)
        if parts:
            target = f"^{slug}-{'-'.join(parts)}"

    return _format_link(full, target, config.links_style)


def _linkify_article_token(
    token: str,
    known_ids: set[str],
    config: RenderConfig,
    heading_map: dict[str, str] | None = None,
) -> str:
    """Turn a bare token like '5c(4)' into a linked fragment."""
    num_match = re.match(r"(\d+[a-zA-Z]?)(.*)", token)
    if not num_match:
        return token

    article_num = num_match.group(1)
    qual = num_match.group(2)

    article_id = f"Article {article_num}"
    if article_id not in known_ids:
        return token

    slug = _slugify(article_id)
    heading = (heading_map or {}).get(article_id, article_id)
    target = heading  # full heading label
    if qual.strip() and config.add_block_links:
        parts = _extract_qualifier_parts(qual)
        if parts:
            target = f"^{slug}-{'-'.join(parts)}"

    return _format_link(token, target, config.links_style)


def _slugify(text: str) -> str:
    """Convert a section ID like 'Article 5a' into 'article-5a'."""
    return re.sub(r"[\s]+", "-", text.strip().lower())


def _extract_qualifier_parts(qual: str) -> list[str]:
    """Extract qualifier parts from a qualifier string.

    Examples::

        "(1)(a)"             → ["1", "a"]
        " paragraph 5, point (a)" → ["5", "a"]
        "(3), point (b)"     → ["3", "b"]
        ", point 1"          → ["1"]
        ", point (a)"        → ["a"]
    """
    parts: list[str] = []

    # Keyword-based extraction takes priority ("paragraph N", "point X")
    has_keywords = "paragraph" in qual or "point" in qual

    if has_keywords:
        # First, extract any parenthesized items BEFORE the first keyword
        # e.g. "(3), point (b)" → extract "3" from the leading "(3)"
        kw_pos = len(qual)
        for kw in ("paragraph", "point"):
            pos = qual.find(kw)
            if pos >= 0 and pos < kw_pos:
                kw_pos = pos
        prefix = qual[:kw_pos]
        prefix_parens = re.findall(r"\(\s*([a-zA-Z0-9]+)\s*\)", prefix)
        parts.extend(p.lower() for p in prefix_parens)

        # Extract "paragraph N" style
        para_match = re.search(r"paragraph\s+(\d+)", qual)
        if para_match:
            parts.append(para_match.group(1))

        # Extract "point N" or "point (X)" style
        point_match = re.search(r"point\s+\(?\s*([a-zA-Z0-9]+)\s*\)?", qual)
        if point_match:
            parts.append(point_match.group(1).lower())

        return parts

    # Fall back to bare parenthesized items like (1), (a), (iv)
    paren_items = re.findall(r"\(\s*([a-zA-Z0-9]+)\s*\)", qual)
    if paren_items:
        parts.extend(p.lower() for p in paren_items)

    return parts


def _format_link(label: str, target: str, style: str) -> str:
    """Format a link in the requested style.

    For wikilinks the target is used verbatim (Obsidian resolves headings by label).
    For standard markdown links the target is URL-encoded so spaces and special
    characters are safe.
    """
    if style == "wikilinks":
        return f"[[#{target}|{label}]]"
    # URL-encode the fragment for standard markdown (spaces → %20 etc.)
    encoded = quote(target, safe="^-")
    return f"[{label}](#{encoded})"


def _apply_intra_links(
    text: str,
    link_ctx: _LinkContext,
) -> str:
    config = link_ctx.config
    result = text

    if config.resolve_semantic_links:
        result = _resolve_semantic_references(
            result,
            link_ctx.article_ids,
            link_ctx.annex_ids,
            config,
            heading_map=link_ctx.heading_map,
        )
    else:
        # Simple non-semantic linking: wrap known section IDs
        all_ids = link_ctx.article_ids | link_ctx.annex_ids
        for section_id in sorted(all_ids, key=len, reverse=True):
            escaped = re.escape(section_id)
            heading = link_ctx.heading_map.get(section_id, section_id)
            result = re.sub(
                rf"\b({escaped})\b",
                lambda match, h=heading: _maybe_link(
                    match.group(1), h, match.string, match.start(), config.links_style
                ),
                result,
            )

    return result


def _maybe_link(label: str, target: str, source: str, start: int, style: str) -> str:
    if start > 0 and source[start - 1] in {"[", "|"}:
        return label
    if style == "wikilinks":
        return f"[[#{target}|{label}]]"
    encoded = quote(target, safe="^-")
    return f"[{label}](#{encoded})"


def _dict_to_section(data: dict) -> Section:
    paragraphs = []
    for paragraph in data.get("paragraphs", []):
        points = [
            Point(
                marker=point.get("marker", ""),
                style=point.get("style", "other"),
                text=point.get("text", ""),
                subpoints=[
                    Point(
                        marker=subpoint.get("marker", ""),
                        style=subpoint.get("style", "other"),
                        text=subpoint.get("text", ""),
                    )
                    for subpoint in point.get("subpoints", [])
                ],
            )
            for point in paragraph.get("points", [])
        ]
        paragraphs.append(
            Paragraph(
                number=paragraph.get("number", ""),
                text=paragraph.get("text", ""),
                points=points,
            )
        )

    notes = [Note(**note) for note in data.get("notes", [])]
    return Section(
        id=data.get("id", ""),
        title=data.get("title", ""),
        chapter_id=data.get("chapter_id", ""),
        chapter_title=data.get("chapter_title", ""),
        section_id=data.get("section_id", ""),
        section_title=data.get("section_title", ""),
        body=data.get("body", ""),
        paragraphs=paragraphs,
        notes=notes,
    )
