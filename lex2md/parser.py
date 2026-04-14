from __future__ import annotations

import re
from collections import OrderedDict
from html import escape as html_escape

from bs4 import BeautifulSoup, Tag

from .models import (
    EurLexDocument,
    Note,
    Paragraph,
    Point,
    Recital,
    Section,
    document_to_dict,
)


POINT_MARKER_TOKEN = r"(?:\d+[a-zA-Z]?|[a-z]|[A-Z]|[ivxlcdm]{1,6}|[IVXLCDM]{1,6})"


def parse_document_html(
    html_content: str, *, celex: str = "", language: str = "en"
) -> EurLexDocument:
    soup = BeautifulSoup(html_content, "html.parser")

    preamble_text, preamble_notes = _extract_preamble(soup)
    preamble_intro, preamble_recitals = _split_preamble_intro_and_recitals(
        preamble_text
    )
    chapter_map = _extract_article_hierarchy(soup)
    articles = _extract_articles(soup)
    _apply_article_hierarchy(articles, chapter_map)
    final_text, signature_lines = _extract_final_provisions(soup)
    annexes = _extract_annexes(soup)

    return EurLexDocument(
        title=_extract_title(soup),
        preamble=preamble_text,
        preamble_intro=preamble_intro,
        preamble_recitals=preamble_recitals,
        preamble_notes=preamble_notes,
        articles=articles,
        final_text=final_text,
        signature_lines=signature_lines,
        annexes=annexes,
        celex=celex,
        language=language,
    )


def parse_eurlex_html(html_content: str) -> dict:
    """Backward-compatible API returning a dictionary."""
    return document_to_dict(parse_document_html(html_content))


def _extract_title(soup: BeautifulSoup) -> str:
    title_tag = soup.find(["h1", "p"], class_=["ti-main", "eli-title", "Titreobjet_cp"])
    if title_tag:
        return _clean_inline_text(title_tag.get_text(" ", strip=True))

    tit_1 = soup.find("div", id="tit_1")
    if tit_1:
        return _clean_inline_text(tit_1.get_text(" ", strip=True))

    return ""


def _extract_preamble(soup: BeautifulSoup) -> tuple[str, list[Note]]:
    pbl_div = soup.find(
        "div", id=lambda value: isinstance(value, str) and value.startswith("pbl")
    )
    if isinstance(pbl_div, Tag):
        blocks = _collect_block_texts(pbl_div)
        notes = _extract_notes(soup, pbl_div)
        text = _replace_note_markers("\n\n".join(blocks), notes)
        return _clean_block_text(text), notes

    start_tag = soup.find("p", class_="Institutionquiagit")
    end_tag = soup.find("p", class_="Formuledadoption")
    if isinstance(start_tag, Tag) and isinstance(end_tag, Tag):
        collected: list[Tag] = [start_tag]
        blocks: list[str] = [_extract_text_with_note_markers(start_tag)]
        for element in start_tag.find_all_next("p"):
            if element == end_tag:
                break
            collected.append(element)
            text = _extract_text_with_note_markers(element)
            if text:
                blocks.append(text)

        notes = _extract_notes_from_many(soup, collected)
        text = _replace_note_markers("\n\n".join(blocks), notes)
        return _clean_block_text(text), notes

    return "", []


def _split_preamble_intro_and_recitals(preamble: str) -> tuple[str, list[Recital]]:
    if not preamble:
        return "", []

    blocks = [
        segment.strip() for segment in re.split(r"\n{2,}", preamble) if segment.strip()
    ]
    if not blocks:
        return preamble.strip(), []

    intro_blocks: list[str] = []
    recitals: list[Recital] = []
    recital_pattern = re.compile(
        r"^\((?P<number>\d+[a-zA-Z]?)\)\s+(?P<text>.*)$", re.DOTALL
    )

    for block in blocks:
        recital_match = recital_pattern.match(block)
        if recital_match:
            recitals.append(
                Recital(
                    number=recital_match.group("number"),
                    text=recital_match.group("text").strip(),
                )
            )
            continue

        if recitals:
            previous = recitals[-1]
            previous.text = f"{previous.text}\n\n{block}".strip()
            continue

        intro_blocks.append(block)

    return "\n\n".join(intro_blocks).strip(), recitals


def _extract_article_hierarchy(soup: BeautifulSoup) -> dict[str, dict[str, str]]:
    hierarchy: dict[str, dict[str, str]] = {}
    chapter_pattern = re.compile(r"^(CHAPTER\s+[A-Z0-9IVXLCDM]+)", re.IGNORECASE)
    section_pattern = re.compile(r"^(SECTION\s+[A-Z0-9IVXLCDM]+)", re.IGNORECASE)

    for chapter_div in soup.find_all(
        "div",
        id=lambda value: (
            isinstance(value, str) and re.match(r"^cpt_[A-Z0-9IVX]+$", value)
        ),
    ):
        chapter_id, chapter_title = _extract_container_heading(
            chapter_div, chapter_pattern
        )

        for section_div in chapter_div.find_all(
            "div",
            id=lambda value: (
                isinstance(value, str)
                and re.match(r"^cpt_[A-Z0-9IVX]+\.sct_[A-Z0-9IVX]+$", value)
            ),
            recursive=False,
        ):
            section_id, section_title = _extract_container_heading(
                section_div, section_pattern
            )
            for article_div in _find_article_subdivisions(section_div):
                article_id = article_div.get("id")
                if not isinstance(article_id, str):
                    continue
                hierarchy[article_id] = {
                    "chapter_id": chapter_id,
                    "chapter_title": chapter_title,
                    "section_id": section_id,
                    "section_title": section_title,
                }

        section_id = ""
        section_title = ""

        for child in chapter_div.find_all(recursive=False):
            if not isinstance(child, Tag):
                continue

            child_id = child.get("id")
            if isinstance(child_id, str) and re.match(
                r"^cpt_[A-Z0-9IVX]+\.sct_[A-Z0-9IVX]+$", child_id
            ):
                continue

            if child.name == "p" and (
                _has_class(child.get("class", []), "oj-ti-grseq-1")
                or _has_class(child.get("class", []), "oj-ti-section-1")
            ):
                heading = _clean_inline_text(child.get_text(" ", strip=True))
                section_match = section_pattern.match(heading)
                if section_match:
                    section_id = section_match.group(1)
                    section_title = ""
                    continue
                if section_id and not section_title:
                    section_title = heading
                    continue

            if child.name == "p" and (
                _has_class(child.get("class", []), "oj-ti-grseq-2")
                or _has_class(child.get("class", []), "oj-ti-section-2")
            ):
                if section_id:
                    section_title = _clean_inline_text(child.get_text(" ", strip=True))
                    continue

            if not isinstance(child_id, str) or not child_id.startswith("art"):
                continue

            hierarchy[child_id] = {
                "chapter_id": chapter_id,
                "chapter_title": chapter_title,
                "section_id": section_id,
                "section_title": section_title,
            }

    return hierarchy


def _extract_container_heading(
    container: Tag, pattern: re.Pattern[str]
) -> tuple[str, str]:
    heading = ""
    title = ""

    for child in container.find_all(recursive=False):
        if not isinstance(child, Tag):
            continue

        text = _clean_inline_text(child.get_text(" ", strip=True))
        if not heading:
            match = pattern.match(text)
            if match:
                heading = match.group(1)
                continue

        if not title and (
            _has_class(child.get("class", []), "eli-title")
            or _has_class(child.get("class", []), "oj-ti-section-2")
            or _has_class(child.get("class", []), "oj-ti-grseq-2")
        ):
            title = text

    return heading, title


def _find_article_subdivisions(container: Tag) -> list[Tag]:
    return container.find_all(
        "div",
        class_=lambda classes: _has_class(classes, "eli-subdivision"),
        id=lambda value: isinstance(value, str) and value.startswith("art"),
    )


def _apply_article_hierarchy(
    articles: list[Section], chapter_map: dict[str, dict[str, str]]
) -> None:
    for article in articles:
        article_anchor = (
            article.anchor.replace("article-", "art_") if article.anchor else ""
        )
        mapping = chapter_map.get(article_anchor)
        if mapping:
            article.chapter_id = mapping.get("chapter_id", "")
            article.chapter_title = mapping.get("chapter_title", "")
            article.section_id = mapping.get("section_id", "")
            article.section_title = mapping.get("section_title", "")
            continue

        article_match = re.search(
            r"Article\s+(\d+[a-zA-Z-]*)", article.id, re.IGNORECASE
        )
        if not article_match:
            continue

        number = article_match.group(1).lower().replace("-", "_")
        fallback_id = f"art_{number}"
        fallback = chapter_map.get(fallback_id)
        if not fallback:
            continue

        article.chapter_id = fallback.get("chapter_id", "")
        article.chapter_title = fallback.get("chapter_title", "")
        article.section_id = fallback.get("section_id", "")
        article.section_title = fallback.get("section_title", "")


def _extract_final_provisions(soup: BeautifulSoup) -> tuple[str, list[str]]:
    final_div = soup.find(
        "div",
        class_=lambda classes: _has_class(classes, "oj-final"),
    )
    if not isinstance(final_div, Tag):
        return "", []

    final_text = ""
    signature_lines: list[str] = []

    for child in final_div.find_all(recursive=False):
        if not isinstance(child, Tag):
            continue

        classes = child.get("class", [])
        if _has_class(classes, "oj-signatory"):
            for line in child.find_all("p"):
                text = _clean_inline_text(line.get_text(" ", strip=True))
                if text:
                    signature_lines.append(text)
            if not signature_lines:
                fallback = _clean_inline_text(child.get_text(" ", strip=True))
                if fallback:
                    signature_lines.append(fallback)
            continue

        text = _clean_inline_text(child.get_text(" ", strip=True))
        if not text:
            continue

        if final_text:
            final_text = f"{final_text}\n\n{text}"
        else:
            final_text = text

    return final_text.strip(), signature_lines


def _extract_articles(soup: BeautifulSoup) -> list[Section]:
    articles: list[Section] = []

    article_divs = soup.find_all(
        "div",
        class_=lambda classes: _has_class(classes, "eli-subdivision"),
        id=lambda value: isinstance(value, str) and value.startswith("art"),
    )

    for div in article_divs:
        section = _extract_section_from_div(
            soup,
            div,
            title_classes=["eli-title"],
            id_pattern=r"^Article\s+\d+[a-zA-Z-]*",
            default_prefix="article",
            parse_paragraphs=True,
        )
        if section:
            articles.append(section)

    if articles:
        return articles

    for tag in soup.find_all("p", class_="Titrearticle"):
        section = _extract_legacy_article(soup, tag)
        if section:
            articles.append(section)

    return articles


def _extract_annexes(soup: BeautifulSoup) -> list[Section]:
    annexes: list[Section] = []
    annex_divs = soup.find_all(
        "div",
        class_=lambda classes: _has_class(classes, "eli-container"),
        id=lambda value: isinstance(value, str) and value.startswith("anx"),
    )

    for div in annex_divs:
        section = _extract_annex_from_div(soup, div)
        if section:
            annexes.append(section)

    return annexes


def _extract_annex_from_div(soup: BeautifulSoup, div: Tag) -> Section | None:
    annex_id = ""
    annex_title = ""
    consumed: set[Tag] = set()

    title_candidates = [
        child
        for child in div.find_all(recursive=False)
        if isinstance(child, Tag)
        and child.name in {"p", "div", "span"}
        and (
            _has_class(child.get("class", []), "oj-doc-ti")
            or _has_class(child.get("class", []), "doc-ti")
            or _has_class(child.get("class", []), "ti-annex")
            or _has_class(child.get("class", []), "eli-title")
        )
    ]

    for candidate in title_candidates:
        text = _clean_inline_text(candidate.get_text(" ", strip=True))
        if not text:
            continue

        if not annex_id and re.match(
            r"^ANNEX\s+[A-Z0-9IVX]+", text, flags=re.IGNORECASE
        ):
            annex_id = text
            consumed.add(candidate)
            continue

        if not annex_title:
            annex_title = text
            consumed.add(candidate)

    blocks: list[str] = []
    pending_section_id = ""
    pending_section_level = 4

    for child in div.find_all(recursive=False):
        if child in consumed:
            continue

        if _is_annex_note_or_separator(child):
            continue

        if _has_class(child.get("class", []), "oj-ti-grseq-1"):
            heading = _clean_inline_text(child.get_text(" ", strip=True))
            if re.match(r"^SECTION\s+[IVXLCDM]+$", heading, flags=re.IGNORECASE):
                pending_section_id = heading
                pending_section_level = 4
                continue

            if pending_section_id:
                blocks.append(
                    f"{'#' * pending_section_level} {pending_section_id} - {heading}"
                )
                pending_section_id = ""
                continue

            blocks.append(f"#### {heading}")
            continue

        if _has_class(child.get("class", []), "oj-ti-grseq-2"):
            heading = _clean_inline_text(child.get_text(" ", strip=True))
            if pending_section_id:
                blocks.append(f"#### {pending_section_id} - {heading}")
                pending_section_id = ""
            elif heading:
                blocks.append(f"##### {heading}")
            continue

        if pending_section_id:
            blocks.append(f"#### {pending_section_id}")
            pending_section_id = ""

        text = _extract_block_text(child)
        if text:
            blocks.append(text)

    if pending_section_id:
        blocks.append(f"#### {pending_section_id}")

    notes = _extract_notes(soup, div)
    raw_body = "\n\n".join(blocks)
    note_prefix = _slugify(annex_id or str(div.get("id", "annex")), prefix="annex")
    namespaced_body, namespaced_notes = _namespace_note_ids(
        raw_body, notes, note_prefix
    )
    body = _replace_note_markers(namespaced_body, namespaced_notes)
    cleaned_body = _clean_block_text(body)

    if not annex_id and not annex_title and not cleaned_body:
        return None

    anchor_source = annex_id or annex_title or "annex"
    return Section(
        id=annex_id,
        title=annex_title,
        body=cleaned_body,
        paragraphs=_extract_article_paragraphs(cleaned_body),
        notes=namespaced_notes,
        anchor=_slugify(anchor_source, prefix="annex"),
    )


def _extract_section_from_div(
    soup: BeautifulSoup,
    div: Tag,
    *,
    title_classes: list[str],
    id_pattern: str,
    default_prefix: str,
    id_classes: list[str] | None = None,
    parse_paragraphs: bool = False,
) -> Section | None:
    id_classes = id_classes or ["ti-art", "eli-title-1"]

    id_tag = _find_first_by_classes(div, ["p", "div", "span"], id_classes)
    title_tag = _find_first_by_classes(div, ["p", "div", "span"], title_classes)

    section_id = _clean_inline_text(id_tag.get_text(" ", strip=True)) if id_tag else ""
    section_title = (
        _clean_inline_text(title_tag.get_text(" ", strip=True)) if title_tag else ""
    )

    blocks: list[str] = []
    for child in div.find_all(recursive=False):
        if child == id_tag or child == title_tag:
            continue
        text = _extract_block_text(child)
        if text:
            blocks.append(text)

    if not section_id:
        inferred = _infer_section_id(blocks, id_pattern)
        if inferred:
            section_id = inferred
            if blocks and blocks[0].startswith(inferred):
                blocks[0] = blocks[0][len(inferred) :].strip(" -:\n")

    notes = _extract_notes(soup, div)
    body = _replace_note_markers("\n\n".join(blocks), notes)
    cleaned_body = _clean_block_text(body)

    if not section_id and not section_title and not cleaned_body:
        return None

    anchor_source = section_id or section_title or default_prefix
    return Section(
        id=section_id,
        title=section_title,
        body=cleaned_body,
        paragraphs=_extract_article_paragraphs(cleaned_body)
        if parse_paragraphs
        else [],
        notes=notes,
        anchor=_slugify(anchor_source, prefix=default_prefix),
    )


def _extract_legacy_article(soup: BeautifulSoup, tag: Tag) -> Section | None:
    section_id = ""
    section_title = ""

    span = tag.find("span")
    if span:
        section_id = _clean_inline_text(span.get_text(" ", strip=True))
        section_title = (
            _clean_inline_text(tag.get_text(" ", strip=True))
            .replace(section_id, "", 1)
            .strip()
        )

    blocks: list[str] = []
    siblings: list[Tag] = [tag]
    for sibling in tag.find_next_siblings():
        sibling_classes = sibling.get("class", [])
        if sibling.name == "p" and any(
            cls in sibling_classes for cls in ["Titrearticle", "Applicationdirecte"]
        ):
            break
        text = _extract_block_text(sibling)
        if text:
            blocks.append(text)
            siblings.append(sibling)

    notes = _extract_notes_from_many(soup, siblings)
    body = _replace_note_markers("\n\n".join(blocks), notes)
    cleaned_body = _clean_block_text(body)

    if not section_id and blocks:
        inferred = _infer_section_id(blocks, r"^Article\s+\d+[a-zA-Z-]*")
        if inferred:
            section_id = inferred

    if not section_id and not section_title and not cleaned_body:
        return None

    return Section(
        id=section_id,
        title=section_title,
        body=cleaned_body,
        paragraphs=_extract_article_paragraphs(cleaned_body),
        notes=notes,
        anchor=_slugify(section_id or section_title or "article", prefix="article"),
    )


def _extract_notes(soup: BeautifulSoup, container: Tag | None) -> list[Note]:
    if not container:
        return []

    notes: "OrderedDict[str, Note]" = OrderedDict()
    for note_tag in container.find_all(
        "span",
        class_=lambda classes: (
            _has_class(classes, "oj-note-tag") and _has_class(classes, "oj-super")
        ),
    ):
        if not isinstance(note_tag, Tag):
            continue
        link = note_tag.find("a") or note_tag.find_parent("a")
        if not isinstance(link, Tag) or not _is_footnote_anchor(link):
            continue

        href = str(link["href"])
        raw_id = _clean_inline_text(note_tag.get_text(" ", strip=True))
        note_id = _normalize_note_id(raw_id) or _normalize_note_id(href.lstrip("#"))
        target_id = href.lstrip("#")
        target = soup.find(id=target_id)
        if not isinstance(target, Tag) or not note_id:
            continue

        holder = target.find_parent(["p", "dd", "li"])
        if not isinstance(holder, Tag):
            continue

        text = _clean_inline_text(holder.get_text(" ", strip=True))
        text = re.sub(rf"^\(?{re.escape(note_id)}\)?\s*", "", text).strip()
        if text and note_id not in notes:
            notes[note_id] = Note(id=note_id, text=text)

    return list(notes.values())


def _extract_notes_from_many(soup: BeautifulSoup, containers: list[Tag]) -> list[Note]:
    dedup: "OrderedDict[str, Note]" = OrderedDict()
    for container in containers:
        for note in _extract_notes(soup, container):
            if note.id not in dedup:
                dedup[note.id] = note
    return list(dedup.values())


def _collect_block_texts(container: Tag) -> list[str]:
    blocks: list[str] = []
    for child in container.find_all(recursive=False):
        text = _extract_block_text(child)
        if text:
            blocks.append(text)

    if blocks:
        return blocks

    fallback = _clean_inline_text(container.get_text(" ", strip=True))
    return [fallback] if fallback else []


def _extract_block_text(node: Tag) -> str:
    if node.name == "table":
        return _extract_markdown_table(node)

    if node.name in {"ul", "ol"}:
        items = []
        for li in node.find_all("li", recursive=False):
            text = _extract_text_with_note_markers(li)
            if text:
                items.append(f"- {text}")
        return "\n".join(items)

    return _extract_text_with_note_markers(node)


def _extract_markdown_table(table: Tag) -> str:
    table_notes: list[str] = []

    for note_node in table.find_all(
        class_=lambda classes: _has_class(classes, "oj-tblnote")
    ):
        note_text = _extract_text_with_note_markers(note_node)
        if note_text and note_text not in table_notes:
            table_notes.append(note_text)

    table_rows: list[tuple[list[tuple[str, int, int]], bool]] = []
    has_span_cells = False
    for tr in table.find_all("tr"):
        if _has_class(tr.get("class", []), "oj-tblnote"):
            continue

        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            cells = tr.find_all(["th", "td"])

        row_cells: list[tuple[str, int, int]] = []
        skip_row = False
        row_has_header = False
        for cell in cells:
            if _has_class(cell.get("class", []), "oj-tblnote"):
                note_text = _extract_text_with_note_markers(cell)
                if note_text and note_text not in table_notes:
                    table_notes.append(note_text)
                skip_row = True
                continue

            text = _extract_text_with_note_markers(cell)
            colspan_raw = str(cell.get("colspan", "1"))
            rowspan_raw = str(cell.get("rowspan", "1"))
            try:
                colspan = max(1, int(colspan_raw))
            except ValueError:
                colspan = 1
            try:
                rowspan = max(1, int(rowspan_raw))
            except ValueError:
                rowspan = 1

            if colspan > 1 or rowspan > 1:
                has_span_cells = True

            row_cells.append((text, colspan, rowspan))
            row_has_header = row_has_header or cell.name == "th"

        if row_cells and not skip_row:
            table_rows.append((row_cells, row_has_header))

    if not table_rows:
        return "\n".join(table_notes)

    if has_span_cells:
        rendered_html = _render_complex_table_as_html(table)
        if not table_notes:
            return rendered_html
        return rendered_html + "\n\n" + "\n".join(table_notes)

    normalized_rows, header_flags = _normalize_table_rows(table_rows)
    if not normalized_rows:
        return "\n".join(table_notes)

    if len(normalized_rows[0]) == 1:
        rendered_single_column = _render_single_column_table(normalized_rows)
        if not table_notes:
            return rendered_single_column
        if rendered_single_column:
            return rendered_single_column + "\n\n" + "\n".join(table_notes)
        return "\n".join(table_notes)

    rendered_points = _render_point_like_table(normalized_rows, header_flags)
    if rendered_points:
        if not table_notes:
            return rendered_points
        return rendered_points + "\n\n" + "\n".join(table_notes)

    columns = len(normalized_rows[0])
    header_index = next((index for index, flag in enumerate(header_flags) if flag), 0)

    header = normalized_rows[header_index]
    body = normalized_rows[:header_index] + normalized_rows[header_index + 1 :]

    if not any(cell.strip() for cell in header):
        header = [f"Column {index + 1}" for index in range(columns)]

    if not body:
        body = []

    def format_row(cells: list[str]) -> str:
        escaped = [cell.replace("|", r"\|") for cell in cells]
        return "| " + " | ".join(escaped) + " |"

    table_lines = [format_row(header), "| " + " | ".join(["---"] * columns) + " |"]
    table_lines.extend(format_row(row) for row in body)

    rendered_table = "\n".join(table_lines)
    if not table_notes:
        return rendered_table
    return rendered_table + "\n\n" + "\n".join(table_notes)


def _normalize_table_rows(
    table_rows: list[tuple[list[tuple[str, int, int]], bool]],
) -> tuple[list[list[str]], list[bool]]:
    grid: list[list[str]] = []
    header_flags: list[bool] = []

    for row_index, (cells, row_has_header) in enumerate(table_rows):
        while len(grid) <= row_index:
            grid.append([])
            header_flags.append(False)

        header_flags[row_index] = header_flags[row_index] or row_has_header
        col_index = 0

        for text, colspan, rowspan in cells:
            while col_index < len(grid[row_index]) and grid[row_index][col_index] != "":
                col_index += 1

            for target_row_index in range(row_index, row_index + rowspan):
                while len(grid) <= target_row_index:
                    grid.append([])
                    header_flags.append(False)

                target_row = grid[target_row_index]
                required_width = col_index + colspan
                if len(target_row) < required_width:
                    target_row.extend([""] * (required_width - len(target_row)))

                for target_col_index in range(col_index, col_index + colspan):
                    if not target_row[target_col_index]:
                        target_row[target_col_index] = text

            col_index += colspan

    if not grid:
        return [], []

    width = max(len(row) for row in grid)
    normalized_rows = [row + [""] * (width - len(row)) for row in grid]
    normalized_headers = header_flags + [False] * (
        len(normalized_rows) - len(header_flags)
    )
    return normalized_rows, normalized_headers[: len(normalized_rows)]


def _render_single_column_table(rows: list[list[str]]) -> str:
    lines = [row[0].strip() for row in rows if row and row[0].strip()]
    return "\n\n".join(lines)


def _render_complex_table_as_html(table: Tag) -> str:
    lines = ["<table>"]
    previous_row_texts: list[str] = []
    previous_row_has_spans = False

    for tr in table.find_all("tr"):
        if _has_class(tr.get("class", []), "oj-tblnote"):
            continue

        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            cells = tr.find_all(["th", "td"])

        rendered_cells: list[str] = []
        row_texts: list[str] = []
        row_has_spans = False
        for cell in cells:
            if _has_class(cell.get("class", []), "oj-tblnote"):
                continue

            tag_name = "th" if cell.name == "th" else "td"
            attrs: list[str] = []

            colspan_raw = str(cell.get("colspan", "1"))
            rowspan_raw = str(cell.get("rowspan", "1"))
            try:
                colspan = max(1, int(colspan_raw))
            except ValueError:
                colspan = 1
            try:
                rowspan = max(1, int(rowspan_raw))
            except ValueError:
                rowspan = 1

            if colspan > 1:
                attrs.append(f' colspan="{colspan}"')
            if rowspan > 1:
                attrs.append(f' rowspan="{rowspan}"')
            row_has_spans = row_has_spans or colspan > 1 or rowspan > 1

            text = _extract_text_with_note_markers(cell)
            row_texts.append(text)
            text_html = html_escape(text).replace("\n", "<br>")
            rendered_cells.append(
                f"<{tag_name}{''.join(attrs)}>{text_html}</{tag_name}>"
            )

        if not rendered_cells:
            continue

        if _is_redundant_split_row(
            previous_row_texts,
            row_texts,
            previous_row_has_spans=previous_row_has_spans,
        ):
            continue

        lines.append("  <tr>")
        lines.extend(f"    {cell_html}" for cell_html in rendered_cells)
        lines.append("  </tr>")

        previous_row_texts = row_texts
        previous_row_has_spans = row_has_spans

    lines.append("</table>")
    return "\n".join(lines)


def _is_redundant_split_row(
    previous_row_texts: list[str],
    current_row_texts: list[str],
    *,
    previous_row_has_spans: bool,
) -> bool:
    if not previous_row_texts:
        return False
    if len(current_row_texts) != 2:
        return False

    previous_last = _normalize_cell_text(previous_row_texts[-1])
    current_combined = _normalize_cell_text(
        f"{current_row_texts[0]} {current_row_texts[1]}"
    )
    if not previous_last or previous_last != current_combined:
        return False

    first_part = _normalize_cell_text(current_row_texts[0])
    if not first_part or not previous_last.startswith(first_part):
        return False

    if previous_row_has_spans:
        return True

    return bool(re.fullmatch(r"[A-Za-z]?\d+(?:\.\d+)*[A-Za-z]?", first_part))


def _normalize_cell_text(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    normalized = re.sub(r"\s*([,;:.])\s*", r"\1", normalized)
    return normalized


def _render_point_like_table(rows: list[list[str]], header_flags: list[bool]) -> str:
    if not rows or len(rows[0]) < 2:
        return ""

    start = 0
    if header_flags and header_flags[0]:
        start = 1
    elif _looks_like_header_row(rows[0]) and not _is_point_marker_cell(rows[0][0]):
        start = 1

    lines: list[str] = []
    for row in rows[start:]:
        marker = row[0].strip()
        if not _is_point_marker_cell(marker):
            return ""

        content_cells = [cell.strip() for cell in row[1:] if cell.strip()]
        content_parts: list[str] = []
        for cell in content_cells:
            if not content_parts or content_parts[-1] != cell:
                content_parts.append(cell)

        content = " ".join(content_parts)
        if not content:
            return ""
        lines.append(f"{marker} {content}")

    return "\n".join(lines) if lines else ""


def _looks_like_header_row(row: list[str]) -> bool:
    non_empty = [cell.strip() for cell in row if cell.strip()]
    if len(non_empty) < 2:
        return False
    return all(len(cell.split()) <= 6 for cell in non_empty)


def _is_point_marker_cell(value: str) -> bool:
    marker = value.strip()
    if not marker:
        return False
    if marker in {"-", "—"}:
        return True
    if re.fullmatch(rf"\({POINT_MARKER_TOKEN}\)", marker):
        return True
    return bool(re.fullmatch(r"\d+[a-zA-Z]?[.)]", marker))


def _extract_table_points(text: str) -> tuple[str, list[Point]]:
    lines = text.splitlines()
    if not lines:
        return "", []

    table_lines = [
        line
        for line in lines
        if line.strip().startswith("|") and line.strip().endswith("|")
    ]
    if not table_lines:
        return text.strip(), []

    separator_pattern = re.compile(r"^\|[-:\s|]+\|$")
    row_pattern = re.compile(
        rf"^\|\s*(?P<marker>\({POINT_MARKER_TOKEN}\)|[-—])\s*\|\s*(?P<content>.+?)\s*\|$"
    )

    has_point_rows = False
    has_non_point_rows = False
    for line in table_lines:
        stripped = line.strip()
        if separator_pattern.match(stripped):
            continue
        if row_pattern.match(stripped):
            has_point_rows = True
            continue
        has_non_point_rows = True
        break

    if not has_point_rows or has_non_point_rows:
        return text.strip(), []

    points: list[Point] = []
    remaining_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if separator_pattern.match(stripped):
            continue

        match = row_pattern.match(stripped)
        if not match:
            remaining_lines.append(line)
            continue

        marker = match.group("marker")
        content = _clean_inline_text(match.group("content"))
        if content:
            points.append(
                Point(marker=marker, style=_classify_point_style(marker), text=content)
            )

    return "\n".join(remaining_lines).strip(), points


def _is_annex_note_or_separator(node: Tag) -> bool:
    classes = node.get("class", [])
    if node.name == "hr" and _has_class(classes, "oj-note"):
        return True
    return _has_class(classes, "oj-note")


def _find_first_by_classes(
    container: Tag, names: list[str], classes: list[str]
) -> Tag | None:
    for class_name in classes:
        tag = container.find(names, class_=class_name)
        if isinstance(tag, Tag):
            return tag
    return None


def _infer_section_id(blocks: list[str], pattern: str) -> str:
    if not blocks:
        return ""
    match = re.match(pattern, blocks[0], flags=re.IGNORECASE)
    if not match:
        return ""
    return _clean_inline_text(match.group(0))


def _replace_note_markers(text: str, notes: list[Note]) -> str:
    updated = text
    for note in notes:
        updated = updated.replace(_note_token(note.id), f"[^{note.id}]")
    updated = re.sub(r"\[\[FN:([A-Za-z0-9_-]+)\]\]", r"(\1)", updated)
    normalized_lines: list[str] = []
    for line in updated.splitlines():
        match = re.match(r"^[ \t]*", line)
        leading = match.group(0) if match else ""
        content = line[len(leading) :]
        content = re.sub(r"[ \t]+", " ", content)
        normalized_lines.append(f"{leading}{content}".rstrip())
    updated = "\n".join(normalized_lines)
    return updated.strip()


def _namespace_note_ids(
    body: str, notes: list[Note], prefix: str
) -> tuple[str, list[Note]]:
    if not notes:
        return body, notes

    updated_body = body
    updated_notes: list[Note] = []
    for note in notes:
        namespaced_id = f"{prefix}-{note.id}"
        updated_body = updated_body.replace(
            _note_token(note.id), _note_token(namespaced_id)
        )
        updated_notes.append(Note(id=namespaced_id, text=note.text))

    return updated_body, updated_notes


def _extract_text_with_note_markers(node: Tag) -> str:
    clone_soup = BeautifulSoup(str(node), "html.parser")
    clone_node = clone_soup.find()
    if not isinstance(clone_node, Tag):
        return ""

    for note_tag in clone_node.find_all(
        "span",
        class_=lambda classes: (
            _has_class(classes, "oj-note-tag") and _has_class(classes, "oj-super")
        ),
    ):
        note_id = _extract_note_id_from_marker(note_tag)
        if note_id:
            note_tag.replace_with(f" {_note_token(note_id)} ")

    return _clean_inline_text(clone_node.get_text(" ", strip=True))


def _extract_note_id_from_marker(note_tag: Tag) -> str:
    link = note_tag.find("a") or note_tag.find_parent("a")
    if not isinstance(link, Tag) or not _is_footnote_anchor(link):
        return ""

    note_id = _normalize_note_id(note_tag.get_text(" ", strip=True))
    if note_id:
        return note_id

    href = str(link.get("href", ""))
    extracted = _normalize_note_id(href.lstrip("#"))
    if extracted:
        return extracted

    link_id = str(link.get("id", ""))
    return _normalize_note_id(link_id)


def _note_token(note_id: str) -> str:
    return f"[[FN:{note_id}]]"


def _is_footnote_anchor(link: Tag) -> bool:
    href = str(link.get("href", ""))
    link_id = str(link.get("id", ""))
    return bool(href.startswith("#ntr") and re.match(r"^ntc\d+-", link_id))


def _normalize_note_id(value: str) -> str:
    text = value.strip().strip("()")
    match = re.search(r"\d+[a-zA-Z]*", text)
    return match.group(0) if match else ""


def _clean_inline_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u00a0", " ").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[‘]([^’]+)[’]", r"`\1`", text)
    return text.strip()


def _clean_block_text(text: str) -> str:
    if not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_article_paragraphs(body: str) -> list[Paragraph]:
    if not body:
        return []

    blocks = [
        segment.strip() for segment in re.split(r"\n{2,}", body) if segment.strip()
    ]
    if not blocks:
        return []

    raw_paragraphs: list[tuple[str, str]] = []

    for block in blocks:
        explicit_dot = re.match(
            r"^(?P<number>\d+[a-zA-Z]?)\.\s+(?P<text>.*)$", block, re.DOTALL
        )
        if explicit_dot:
            number = explicit_dot.group("number")
            text = explicit_dot.group("text").strip()
            raw_paragraphs.append((number, text))
            continue

        explicit_paren = re.match(
            r"^\((?P<number>\d+[a-zA-Z]?)\)\s+(?P<text>.*)$",
            block,
            re.DOTALL,
        )
        if explicit_paren:
            if raw_paragraphs and (
                _is_introductory_paragraph(raw_paragraphs[-1][1])
                or (
                    raw_paragraphs[-1][0] == ""
                    and _contains_parenthesized_points(raw_paragraphs[-1][1])
                )
            ):
                previous_number, previous_text = raw_paragraphs[-1]
                combined = f"{previous_text}\n\n{block}".strip()
                raw_paragraphs[-1] = (previous_number, combined)
                continue

            number = explicit_paren.group("number")
            text = explicit_paren.group("text").strip()
            raw_paragraphs.append((number, text))
            continue

        if raw_paragraphs and _is_paragraph_continuation(block):
            previous_number, previous_text = raw_paragraphs[-1]
            combined = f"{previous_text}\n\n{block}".strip()
            raw_paragraphs[-1] = (previous_number, combined)
            continue

        raw_paragraphs.append(("", block))

    paragraphs: list[Paragraph] = []
    for number, text in raw_paragraphs:
        paragraph_text, points = _extract_points(text)
        paragraphs.append(Paragraph(number=number, text=paragraph_text, points=points))

    return paragraphs


def _is_paragraph_continuation(block: str) -> bool:
    stripped = block.lstrip()
    return bool(
        stripped.startswith("|")
        or stripped.startswith("- ")
        or stripped.startswith("— ")
        or re.match(rf"^\({POINT_MARKER_TOKEN}\)\s+", stripped)
    )


def _is_introductory_paragraph(text: str) -> bool:
    stripped = text.rstrip()
    return stripped.endswith(":") or stripped.endswith(";")


def _contains_parenthesized_points(text: str) -> bool:
    return bool(re.search(r"\(\d+[a-zA-Z]?\)\s+", text))


def _extract_points(text: str) -> tuple[str, list[Point]]:
    without_tables, table_points = _extract_table_points(text)
    without_dashes, dash_points = _extract_dash_points(without_tables)
    lead_text, inline_points = _extract_inline_points(without_dashes)

    points = _deduplicate_points([*table_points, *dash_points, *inline_points])
    paragraph_text = lead_text if inline_points else without_dashes.strip()
    return paragraph_text, points


def _deduplicate_points(points: list[Point]) -> list[Point]:
    deduped: list[Point] = []
    seen: set[tuple[str, str]] = set()

    for point in points:
        normalized_text = re.sub(r"\s+", " ", point.text).strip().rstrip(";.")
        key = (point.marker.strip(), normalized_text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(point)

    return deduped


def _extract_dash_points(text: str) -> tuple[str, list[Point]]:
    points: list[Point] = []
    remaining_lines: list[str] = []

    for line in text.splitlines():
        match = re.match(r"^\s*(?P<marker>[-—])\s+(?P<content>.+)$", line)
        if not match:
            remaining_lines.append(line)
            continue

        content = _clean_inline_text(match.group("content"))
        if content:
            marker = match.group("marker")
            points.append(
                Point(marker=marker, style=_classify_point_style(marker), text=content)
            )

    return "\n".join(remaining_lines).strip(), points


def _extract_inline_points(text: str) -> tuple[str, list[Point]]:
    pattern = re.compile(rf"(?P<marker>\({POINT_MARKER_TOKEN}\))\s+")
    candidate_matches = [
        match
        for match in pattern.finditer(text)
        if _is_point_marker_start(text, match.start())
    ]
    if len(candidate_matches) < 2:
        return text.strip(), []

    primary_style = _classify_point_style(candidate_matches[0].group("marker"))
    filtered_candidates: list[re.Match[str]] = [candidate_matches[0]]
    for match in candidate_matches[1:]:
        if _should_skip_nested_roman_candidate(
            text,
            marker_match=match,
            previous_match=filtered_candidates[-1],
            primary_style=primary_style,
        ):
            continue
        filtered_candidates.append(match)

    matches = [
        match
        for match in filtered_candidates
        if _is_same_point_level(
            _classify_point_style(match.group("marker")), primary_style
        )
    ]
    if len(matches) < 2:
        return text.strip(), []

    lead = text[: matches[0].start()].strip()
    points: list[Point] = []

    for index, match in enumerate(matches):
        content_start = match.end()
        content_end = (
            matches[index + 1].start() if index + 1 < len(matches) else len(text)
        )
        content = text[content_start:content_end].strip()
        if not content:
            continue

        marker = match.group("marker")
        content, subpoints = _extract_nested_subpoints(content)
        points.append(
            Point(
                marker=marker,
                style=_classify_point_style(marker),
                text=content,
                subpoints=subpoints,
            )
        )

    return lead, points


def _is_same_point_level(style: str, primary_style: str) -> bool:
    if style == primary_style:
        return True
    return {style, primary_style} <= {"arabic", "arabic_alpha"}


def _should_skip_nested_roman_candidate(
    text: str,
    *,
    marker_match: re.Match[str],
    previous_match: re.Match[str],
    primary_style: str,
) -> bool:
    if primary_style not in {"lower_alpha", "upper_alpha"}:
        return False

    token = marker_match.group("marker").strip().strip("()")
    if not re.fullmatch(r"[ivxlcdm]+|[IVXLCDM]+", token):
        return False

    between = text[previous_match.end() : marker_match.start()]
    if not between:
        return False

    return ":" in between


def _extract_nested_subpoints(text: str) -> tuple[str, list[Point]]:
    subpoint_pattern = re.compile(
        rf"(?P<marker>\((?:[ivxlcdm]{{1,6}}|[IVXLCDM]{{1,6}}|\d+[a-zA-Z]?)\))\s+"
    )
    matches = [
        match
        for match in subpoint_pattern.finditer(text)
        if _is_point_marker_start(text, match.start())
    ]
    if len(matches) < 2:
        return text, []

    lead = text[: matches[0].start()].rstrip()
    subpoints: list[Point] = []

    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        subpoint_text = text[start:end].strip()
        if not subpoint_text:
            continue

        marker = match.group("marker")
        subpoints.append(
            Point(
                marker=marker,
                style=_classify_point_style(marker),
                text=subpoint_text,
            )
        )

    if not subpoints:
        return text, []

    return lead, subpoints


def _classify_point_style(marker: str) -> str:
    if marker in {"-", "—"}:
        return "dash"

    token = marker.strip().strip("()")
    if re.fullmatch(r"\d+", token):
        return "arabic"
    if re.fullmatch(r"\d+[a-zA-Z]", token):
        return "arabic_alpha"
    if token.isalpha() and token.islower():
        if len(token) > 1 and re.fullmatch(r"[ivxlcdm]+", token):
            return "lower_roman"
        return "lower_alpha"
    if token.isalpha() and token.isupper():
        if len(token) > 1 and re.fullmatch(r"[IVXLCDM]+", token):
            return "upper_roman"
        return "upper_alpha"
    return "other"


def _is_point_marker_start(text: str, position: int) -> bool:
    index = position - 1
    while index >= 0 and text[index].isspace():
        index -= 1
    if index < 0:
        return True

    if text[index] in {":", ";", ".", "\n", ","}:
        return True

    word_end = index
    while word_end >= 0 and text[word_end].isalpha():
        word_end -= 1
    connector = text[word_end + 1 : index + 1].lower()
    if connector in {"and", "or", "et", "ou", "y", "e"}:
        delimiter_index = word_end
        while delimiter_index >= 0 and text[delimiter_index].isspace():
            delimiter_index -= 1
        if delimiter_index < 0:
            return True
        return text[delimiter_index] in {":", ";", ".", "\n", ","}

    return False


def _slugify(value: str, *, prefix: str = "section") -> str:
    slug = value.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug).strip("-")
    return slug or prefix


def _has_class(classes: object, class_name: str) -> bool:
    if classes is None:
        return False
    if isinstance(classes, str):
        return class_name in classes.split()
    if isinstance(classes, (list, tuple, set)):
        return class_name in classes
    return False
