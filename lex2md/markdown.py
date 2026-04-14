from __future__ import annotations

import re

from .models import EurLexDocument, Note, Paragraph, Point, Recital, Section


def generate_markdown(document: EurLexDocument | dict) -> str:
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

    parts: list[str] = []

    if parsed.title:
        parts.append(f"# {parsed.title}")
        parts.append("")

    if parsed.celex:
        parts.append(f"- CELEX: `{parsed.celex}`")
        parts.append(f"- Language: `{parsed.language}`")
        parts.append("")

    nav_lines = _build_navigation(parsed)
    if nav_lines:
        parts.extend(nav_lines)
        parts.append("")

    if parsed.preamble:
        parts.append("## Preamble")
        parts.append("")
        parts.append(_apply_intra_links(parsed.preamble, article_links, annex_links))
        notes = _format_notes(parsed.preamble_notes)
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

            parts.extend(_render_section(article, heading_level=article_heading_level))

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
            parts.extend(_render_section(annex, heading_level=3))

    return "\n".join(parts).strip()


def _render_section(section: Section, *, heading_level: int) -> list[str]:
    level = "#" * heading_level
    header = _section_header(section)
    lines = [f"{level} {header}"]
    if section.anchor:
        lines.append(f'<a id="{section.anchor}"></a>')
    lines.append("")

    section_content = _render_section_content(section)
    if section_content:
        lines.extend(section_content)

    notes = _format_notes(section.notes)
    if notes:
        lines.append("")
        lines.append(notes)

    lines.append("")
    return lines


def _section_header(section: Section) -> str:
    parts = [part for part in [section.id, section.title] if part]
    return " - ".join(parts) if parts else "Section"


def _render_group_heading(
    group_id: str, group_title: str, *, label: str, level: int
) -> str:
    heading = group_id.strip()
    title = group_title.strip()
    if heading and title:
        content = f"{heading} - {title}"
    else:
        content = heading or title or label
    return f"{'#' * level} {content}"


def _format_notes(notes: list[Note]) -> str:
    if not notes:
        return ""
    lines = ["---", ""]
    for note in notes:
        lines.append(f"[^{note.id}]: {note.text}")
    return "\n".join(lines)


def _render_section_content(section: Section) -> list[str]:
    if section.paragraphs:
        return _render_paragraphs(section.paragraphs)
    if section.body:
        return [section.body]
    return []


def _render_paragraphs(paragraphs: list[Paragraph]) -> list[str]:
    lines: list[str] = []
    total = len(paragraphs)
    for index, paragraph in enumerate(paragraphs):
        prefix = f"{paragraph.number}." if paragraph.number else ""
        text = paragraph.text.strip()
        lines.append(f"{prefix} {text}".strip())
        lines.extend(_render_paragraph_points(paragraph.points))
        if index + 1 < total:
            lines.append("")
    return lines


def _render_paragraph_points(points: list[Point]) -> list[str]:
    filtered = [point for point in points if point.text.strip()]
    if not filtered:
        return []

    lines: list[str] = []
    for point in filtered:
        lines.extend(_render_point_with_nested_dash_list(point, indent=3))
    return lines


def _render_point_with_nested_dash_list(point: Point, *, indent: int) -> list[str]:
    lead_text, nested_items = _split_inline_dash_items(point.text)
    main_line = f"{' ' * indent}- {_format_point_text(point.marker, lead_text)}"
    lines = [main_line.rstrip()]

    if point.subpoints:
        lines.extend(_render_point_subpoints(point.subpoints, indent=indent + 3))

    lines.extend(_render_nested_dash_items(nested_items, indent=indent + 3))
    return lines


def _render_point_subpoints(subpoints: list[Point], *, indent: int) -> list[str]:
    lines: list[str] = []
    for subpoint in subpoints:
        lines.extend(_render_point_with_nested_dash_list(subpoint, indent=indent))
    return lines


def _render_nested_dash_items(items: list[str], *, indent: int) -> list[str]:
    lines: list[str] = []
    for item in items:
        lead_text, children = _split_inline_dash_items(item)
        item_text = lead_text.strip() if children else item.strip()

        child_indent = indent
        if item_text:
            lines.append(f"{' ' * indent}- {item_text}")
            child_indent = indent + 3

        if children:
            lines.extend(_render_nested_dash_items(children, indent=child_indent))

    return lines


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

    preamble_recitals = [
        Recital(**recital) for recital in document.get("preamble_recitals", [])
    ]
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


def _build_navigation(document: EurLexDocument) -> list[str]:
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
        lines.append(f"- [{label}](#{anchor})")
    return lines


def _apply_intra_links(
    text: str, article_links: dict[str, str], annex_links: dict[str, str]
) -> str:
    result = text

    for section_id, anchor in sorted(
        article_links.items(), key=lambda item: len(item[0]), reverse=True
    ):
        escaped = re.escape(section_id)
        result = re.sub(
            rf"\b({escaped})\b",
            lambda match: _maybe_link(
                match.group(1), anchor, match.string, match.start()
            ),
            result,
        )

    for section_id, anchor in sorted(
        annex_links.items(), key=lambda item: len(item[0]), reverse=True
    ):
        escaped = re.escape(section_id)
        result = re.sub(
            rf"\b({escaped})\b",
            lambda match: _maybe_link(
                match.group(1), anchor, match.string, match.start()
            ),
            result,
        )

    return result


def _maybe_link(label: str, anchor: str, source: str, start: int) -> str:
    if start > 0 and source[start - 1] == "[":
        return label
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
