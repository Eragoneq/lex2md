from __future__ import annotations

import re
from collections import OrderedDict

from bs4 import BeautifulSoup, Tag

from lex2md.models import (
    EurLexDocument,
    Note,
    Recital,
    Section,
    document_to_dict,
)

POINT_MARKER_TOKEN = r"(?:\d+[a-zA-Z]?|[a-z]{1,3}|[A-Z]{1,3}|[ivxlcdm]{1,6}|[IVXLCDM]{1,6})"
from lex2md.parser.points import _extract_article_paragraphs
from lex2md.parser.tables import _extract_markdown_table
from lex2md.parser.text import (
    _clean_block_text,
    _clean_inline_text,
    _extract_text_with_note_markers,
    _has_class,
    _is_footnote_anchor,
    _namespace_note_ids,
    _normalize_note_id,
    _replace_note_markers,
    _slugify,
)


def parse_document_html(
    html_content: str, *, celex: str = "", language: str = "en"
) -> EurLexDocument:
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove consolidated document metadata tags by class
    for tag in soup.find_all(class_="modref"):
        tag.decompose()

    # Remove inline consolidated markers (e.g. ►M2, ▼B, ◄)
    mod_pattern = re.compile(r"^[▼►]\s*[A-Z]\d*$|^◄$")
    for tag in soup.find_all(["span", "a", "p"]):
        text = tag.get_text(strip=True)
        if text and mod_pattern.match(text):
            tag.decompose()

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
        # Derive the chapter_map key from article.id
        # article.id is like "Article 1" → chapter_map key is like "art_1"
        article_match = re.search(
            r"Article\s+(\d+[a-zA-Z-]*)", article.id, re.IGNORECASE
        )
        if not article_match:
            continue

        number = article_match.group(1).lower().replace("-", "_")
        art_key = f"art_{number}"
        mapping = chapter_map.get(art_key)
        if mapping:
            article.chapter_id = mapping.get("chapter_id", "")
            article.chapter_title = mapping.get("chapter_title", "")
            article.section_id = mapping.get("section_id", "")
            article.section_title = mapping.get("section_title", "")



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

    return Section(
        id=annex_id,
        title=annex_title,
        body=cleaned_body,
        paragraphs=_extract_article_paragraphs(cleaned_body),
        notes=namespaced_notes,
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

    return Section(
        id=section_id,
        title=section_title,
        body=cleaned_body,
        paragraphs=_extract_article_paragraphs(cleaned_body)
        if parse_paragraphs
        else [],
        notes=notes,
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
    )

def _extract_notes(soup: BeautifulSoup, container: Tag | None) -> list[Note]:
    if not container:
        return []

    notes: OrderedDict[str, Note] = OrderedDict()
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
    dedup: OrderedDict[str, Note] = OrderedDict()
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
