from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Note:
    id: str
    text: str


@dataclass
class Recital:
    number: str
    text: str


@dataclass
class Point:
    marker: str
    style: str
    text: str
    subpoints: list["Point"] = field(default_factory=list)


@dataclass
class Paragraph:
    number: str
    text: str
    points: list[Point] = field(default_factory=list)


@dataclass
class Section:
    id: str = ""
    title: str = ""
    chapter_id: str = ""
    chapter_title: str = ""
    section_id: str = ""
    section_title: str = ""
    body: str = ""
    paragraphs: list[Paragraph] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    anchor: str = ""


@dataclass
class EurLexDocument:
    title: str = ""
    preamble: str = ""
    preamble_intro: str = ""
    preamble_recitals: list[Recital] = field(default_factory=list)
    preamble_notes: list[Note] = field(default_factory=list)
    articles: list[Section] = field(default_factory=list)
    final_text: str = ""
    signature_lines: list[str] = field(default_factory=list)
    annexes: list[Section] = field(default_factory=list)
    celex: str = ""
    language: str = "en"


def document_to_dict(document: EurLexDocument) -> dict[str, Any]:
    data = asdict(document)
    data["preamble_recitals"] = [
        asdict(recital) for recital in document.preamble_recitals
    ]
    data["preamble_notes"] = [asdict(note) for note in document.preamble_notes]
    data["articles"] = [_section_to_dict(section) for section in document.articles]
    data["annexes"] = [_section_to_dict(section) for section in document.annexes]
    return data


def _section_to_dict(section: Section) -> dict[str, Any]:
    return {
        "id": section.id,
        "title": section.title,
        "chapter_id": section.chapter_id,
        "chapter_title": section.chapter_title,
        "section_id": section.section_id,
        "section_title": section.section_title,
        "body": section.body,
        "paragraphs": [
            {
                "number": paragraph.number,
                "text": paragraph.text,
                "points": [_point_to_dict(point) for point in paragraph.points],
            }
            for paragraph in section.paragraphs
        ],
        "notes": [asdict(note) for note in section.notes],
        "anchor": section.anchor,
    }


def _point_to_dict(point: Point) -> dict[str, Any]:
    return {
        "marker": point.marker,
        "style": point.style,
        "text": point.text,
        "subpoints": [_point_to_dict(subpoint) for subpoint in point.subpoints],
    }
