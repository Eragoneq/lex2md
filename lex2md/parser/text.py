from __future__ import annotations

import re

from bs4 import Tag

from lex2md.models import (
    Note,
)

POINT_MARKER_TOKEN = r"(?:\d+[a-zA-Z]?|[a-z]|[A-Z]|[ivxlcdm]{1,6}|[IVXLCDM]{1,6})"

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
    import copy
    clone_node = copy.copy(node)

    for note_tag in clone_node.find_all(
        "span",
        class_=lambda classes: (
            _has_class(classes, "oj-note-tag") and _has_class(classes, "oj-super")
        ),
    ):
        note_id = _extract_note_id_from_marker(note_tag)
        if note_id:
            # We must create a new NavigableString to replace it safely
            from bs4 import NavigableString
            note_tag.replace_with(NavigableString(f" {_note_token(note_id)} "))

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
