from __future__ import annotations

import re
from dataclasses import dataclass

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
    article_links = {
        section.id: section.anchor
        for section in parsed.articles
        if section.id and section.anchor
    }
    annex_links = {
        section.id: section.anchor
        for section in parsed.annexes
        if section.id and section.anchor
    }
    link_ctx = _LinkContext(article_links, annex_links, config)

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
        preamble_text = _apply_intra_links(preamble_text, article_links, annex_links, config)
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
            article.chapter_id or article.chapter_title or article.section_id or article.section_title
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

            parts.extend(_render_section(article, heading_level=article_heading_level, config=config, link_ctx=link_ctx))

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
        for annex in parsed.annexes:
            parts.extend(_render_section(annex, heading_level=3, config=config, link_ctx=link_ctx))

    return "\n".join(parts).strip()


@dataclass
class _LinkContext:
    """Carries article/annex anchor lookups through the render pipeline."""
    article_links: dict[str, str]
    annex_links: dict[str, str]
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
    ``^id`` anchors.
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
    base_id = section.anchor or "section"
    if section.paragraphs:
        return _render_paragraphs(section.paragraphs, base_id, config, link_ctx)
    if section.body:
        body = section.body
        if config.add_block_links:
            body = _namespace_footnote_refs(body)
        if link_ctx:
            body = _apply_intra_links(
                body, link_ctx.article_links, link_ctx.annex_links, link_ctx.config
            )
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
            text = _apply_intra_links(
                text, link_ctx.article_links, link_ctx.annex_links, link_ctx.config
            )

        p_idx = paragraph.number.lower() if paragraph.number else f"p{index}"
        block_id = f"{base_id}-{p_idx}"

        main_line = f"{prefix} {text}".strip()
        if config.add_block_links:
            main_line += f" ^{block_id}"

        lines.append(main_line)
        lines.extend(_render_paragraph_points(paragraph.points, block_id, config))
        if index + 1 < total:
            lines.append("")
    return lines


def _render_paragraph_points(points: list[Point], parent_id: str, config: RenderConfig) -> list[str]:
    filtered = [point for point in points if point.text.strip()]
    if not filtered:
        return []

    lines: list[str] = []
    for index, point in enumerate(filtered):
        marker_slug = re.sub(r'[^a-zA-Z0-9]', '', point.marker.lower()) if point.marker else f"pt{index}"
        pt_id = f"{parent_id}-{marker_slug}"
        lines.extend(_render_point_with_nested_dash_list(point, pt_id, config, indent=3))
    return lines


def _render_point_with_nested_dash_list(point: Point, block_id: str, config: RenderConfig, *, indent: int) -> list[str]:
    lead_text, nested_items = _split_inline_dash_items(point.text)
    if config.add_block_links:
        lead_text = _namespace_footnote_refs(lead_text)

    main_line = f"{' ' * indent}- {_format_point_text(point.marker, lead_text)}".rstrip()
    if config.add_block_links:
        main_line += f" ^{block_id}"
    lines = [main_line]

    if point.subpoints:
        lines.extend(_render_point_subpoints(point.subpoints, block_id, config, indent=indent + 3))

    lines.extend(_render_nested_dash_items(nested_items, block_id, config, indent=indent + 3))
    return lines


def _render_point_subpoints(subpoints: list[Point], parent_id: str, config: RenderConfig, *, indent: int) -> list[str]:
    lines: list[str] = []
    for index, subpoint in enumerate(subpoints):
        marker_slug = re.sub(r'[^a-zA-Z0-9]', '', subpoint.marker.lower()) if subpoint.marker else f"spt{index}"
        spt_id = f"{parent_id}-{marker_slug}"
        lines.extend(_render_point_with_nested_dash_list(subpoint, spt_id, config, indent=indent))
    return lines


def _render_nested_dash_items(items: list[str], parent_id: str, config: RenderConfig, *, indent: int) -> list[str]:
    lines: list[str] = []
    for index, item in enumerate(items):
        item_id = f"{parent_id}-d{index}"
        lead_text, children = _split_inline_dash_items(item)
        item_text = lead_text.strip() if children else item.strip()
        if config.add_block_links:
            item_text = _namespace_footnote_refs(item_text)

        child_indent = indent
        if item_text:
            line = f"{' ' * indent}- {item_text}"
            if config.add_block_links:
                line += f" ^{item_id}"
            lines.append(line)
            child_indent = indent + 3

        if children:
            lines.extend(_render_nested_dash_items(children, item_id, config, indent=child_indent))

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


def _find_dash_markers(
    text: str, *, allowed_delimiters: set[str]
) -> list[tuple[int, int, str]]:
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
    entries: list[tuple[str, str]] = []

    for section in document.articles:
        if section.anchor:
            entries.append((_section_header(section), section.anchor))
    for section in document.annexes:
        if section.anchor:
            entries.append((_section_header(section), section.anchor))

    if not entries:
        return lines

    lines.append("## Navigation")
    lines.append("")
    for label, anchor in entries:
        lines.append(f"- [[#{anchor}|{label}]]")
    return lines


# ---------------------------------------------------------------------------
# Semantic link resolution
# ---------------------------------------------------------------------------

# Matches "Article 5a", "Articles 5c(4) and 5e(2)", "Article 3 paragraph 5, point (a)"
# but NOT when followed by "of Regulation", "of Directive", etc.
_EXTERNAL_DOC_SUFFIX = r"(?:\s+of\s+(?:Regulation|Directive|Decision|Delegated|Implementing|Commission|Council|European)\b)"

# Pattern for a single article-like reference with optional inline qualifiers.
# Captures:
#   group "base"  – e.g. "Article 5a"
#   group "qual"  – e.g. "(4)" or "(1)(a)" or " paragraph 5, point (a)"
_ARTICLE_REF = (
    r"(?P<base>Article\s+\d+[a-zA-Z]?)"
    r"(?P<qual>"
    r"(?:\s+paragraph\s+\d+(?:,?\s+point\s+\(?[a-zA-Z0-9]+\)?)?)"  # paragraph N, point (x) style
    r"|(?:\(\s*[a-zA-Z0-9]+\s*\))+"                          # (1)(a) style
    r")?"
)

# Pattern for compound "Articles X and Y" references.
_ARTICLES_COMPOUND = (
    r"Articles\s+"
    r"(?P<first>\d+[a-zA-Z]?(?:(?:\(\s*[a-zA-Z0-9]+\s*\))+)?)"
    r"(?:\s+and\s+"
    r"(?P<second>\d+[a-zA-Z]?(?:(?:\(\s*[a-zA-Z0-9]+\s*\))+)?)"
    r")?"
)

# Pattern for annex references with optional ", point N"
_ANNEX_REF = (
    r"(?P<annex_base>(?:ANNEX|Annex)\s+[IVXLCDM]+(?:\s+[A-Z])?)"
    r"(?P<annex_qual>"
    r"(?:,?\s+point\s+\(?\s*[a-zA-Z0-9]+\s*\)?)"     # , point (1) or , point 1
    r"|(?:(?:\(\s*[a-zA-Z0-9]+\s*\))+)"                # (1)(a) style
    r")?"
)


def _is_external_reference(source: str, match_end: int) -> bool:
    """Check if text after the match indicates an external document reference."""
    remainder = source[match_end:]
    return bool(re.match(_EXTERNAL_DOC_SUFFIX, remainder))


def _build_case_insensitive_lookup(
    lookup: dict[str, str],
) -> dict[str, str]:
    """Build a lookup that maps both original and case-folded keys."""
    result: dict[str, str] = {}
    for key, value in lookup.items():
        result[key] = value
        # Also add title-case and upper-case variants
        result[key.upper()] = value
        result[key.title()] = value
        # Handle "Annex IV" / "ANNEX IV" specifically
        if key.startswith("ANNEX"):
            result["Annex" + key[5:]] = value
    return result


def _resolve_semantic_references(
    text: str,
    article_lookup: dict[str, str],
    annex_lookup: dict[str, str],
    config: RenderConfig,
) -> str:
    """Post-process text to resolve human-readable citations into internal links.

    Handles patterns like:
    - "Article 3"  →  link to article-3
    - "Article 3(1)(a)"  →  link to article-3 block ^article-3-1-a
    - "Article 3 paragraph 5, point (a)"  →  link to article-3 block ^article-3-5-a
    - "Articles 5c(4) and 5e(2)"  →  two separate links
    - "Annex IV"  →  link to annex-iv
    - "Annex IV, point 1"  →  link to annex-iv block ^annex-iv-1
    - Skips references followed by "of Regulation..." (external doc)
    """
    result = text
    expanded_annex_lookup = _build_case_insensitive_lookup(annex_lookup)

    # 1. Handle compound "Articles X and Y" first (longer match)
    result = re.sub(
        _ARTICLES_COMPOUND,
        lambda m: _replace_compound_articles(m, article_lookup, config),
        result,
    )

    # 2. Handle single "Article X" references (skip already-linked ones)
    result = re.sub(
        _ARTICLE_REF,
        lambda m: _replace_single_article(m, article_lookup, config),
        result,
    )

    # 3. Handle annex references
    result = re.sub(
        _ANNEX_REF,
        lambda m: _replace_annex_ref(m, expanded_annex_lookup, config),
        result,
    )

    return result


def _replace_compound_articles(
    match: re.Match[str], lookup: dict[str, str], config: RenderConfig
) -> str:
    """Replace 'Articles 5c(4) and 5e(2)' with two individual links."""
    full = match.group(0)
    start = match.start()
    source = match.string
    if start > 0 and source[start - 1] in {"[", "|"}:
        return full
    if _is_external_reference(source, match.end()):
        return full

    first_raw = match.group("first")
    second_raw = match.group("second")

    first_link = _linkify_article_token(first_raw, lookup, config)
    if second_raw:
        second_link = _linkify_article_token(second_raw, lookup, config)
        return f"Articles {first_link} and {second_link}"
    return f"Articles {first_link}"


def _replace_single_article(
    match: re.Match[str],
    lookup: dict[str, str],
    config: RenderConfig,
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
    # After compound replacement the text contains e.g. "Articles [5c(4)]..."
    # but check the *original* source for "Articles " immediately before.
    prefix_start = max(0, start - 9)
    before = source[prefix_start:start]
    if re.search(r"Articles\s*$", before):
        return full

    base = match.group("base")  # "Article 5a"
    qual = match.group("qual") or ""

    anchor = lookup.get(base)
    if not anchor:
        return full

    target = anchor
    if qual.strip() and config.add_block_links:
        parts = _extract_qualifier_parts(qual)
        if parts:
            target = f"^{anchor}-{'-'.join(parts)}"

    return _format_link(full, target, config.links_style)


def _replace_annex_ref(
    match: re.Match[str], lookup: dict[str, str], config: RenderConfig
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

    anchor = lookup.get(annex_base)
    if not anchor:
        return full

    target = anchor
    if annex_qual.strip() and config.add_block_links:
        parts = _extract_qualifier_parts(annex_qual)
        if parts:
            target = f"^{anchor}-{'-'.join(parts)}"

    return _format_link(full, target, config.links_style)


def _linkify_article_token(
    token: str, lookup: dict[str, str], config: RenderConfig
) -> str:
    """Turn a bare token like '5c(4)' into a linked 'Article 5c(4)' fragment."""
    # Split token into number part + qualifier part
    num_match = re.match(r"(\d+[a-zA-Z]?)(.*)", token)
    if not num_match:
        return token

    article_num = num_match.group(1)
    qual = num_match.group(2)

    article_id = f"Article {article_num}"
    anchor = lookup.get(article_id)
    if not anchor:
        return token

    target = anchor
    if qual.strip() and config.add_block_links:
        parts = _extract_qualifier_parts(qual)
        if parts:
            target = f"^{anchor}-{'-'.join(parts)}"

    return _format_link(token, target, config.links_style)


def _extract_qualifier_parts(qual: str) -> list[str]:
    """Extract qualifier parts from a qualifier string.

    Examples::

        "(1)(a)"             → ["1", "a"]
        " paragraph 5, point (a)" → ["5", "a"]
        ", point 1"          → ["1"]
        ", point (a)"        → ["a"]
    """
    parts: list[str] = []

    # Keyword-based extraction takes priority ("paragraph N", "point X")
    has_keywords = "paragraph" in qual or "point" in qual

    if has_keywords:
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
    """Format a link in the requested style."""
    if style == "wikilinks":
        return f"[[#{target}|{label}]]"
    return f"[{label}](#{target})"


def _apply_intra_links(
    text: str, article_links: dict[str, str], annex_links: dict[str, str], config: RenderConfig
) -> str:
    result = text

    if config.resolve_semantic_links:
        result = _resolve_semantic_references(result, article_links, annex_links, config)
    else:
        for section_id, anchor in sorted(article_links.items(), key=lambda item: len(item[0]), reverse=True):
            escaped = re.escape(section_id)
            result = re.sub(
                rf"\b({escaped})\b",
                lambda match: _maybe_link(match.group(1), anchor, match.string, match.start(), config.links_style),
                result,
            )

        for section_id, anchor in sorted(annex_links.items(), key=lambda item: len(item[0]), reverse=True):
            escaped = re.escape(section_id)
            result = re.sub(
                rf"\b({escaped})\b",
                lambda match: _maybe_link(match.group(1), anchor, match.string, match.start(), config.links_style),
                result,
            )

    return result


def _maybe_link(label: str, anchor: str, source: str, start: int, style: str) -> str:
    if start > 0 and source[start - 1] in {"[", "|"}:
        return label
    if style == "wikilinks":
        return f"[[#{anchor}|{label}]]"
    return f"[{label}](#{anchor})"


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
        anchor=data.get("anchor", ""),
    )
