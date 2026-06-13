from __future__ import annotations

import re

from lex2md.models import (
    Paragraph,
    Point,
)

POINT_MARKER_TOKEN = r"(?:\d+[a-zA-Z]?|[a-z]{1,3}|[A-Z]{1,3}|[ivxlcdm]{1,6}|[IVXLCDM]{1,6})"
from lex2md.parser.tables import _extract_table_points
from lex2md.parser.text import _clean_inline_text


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
        rf"(?P<marker>\({POINT_MARKER_TOKEN}\))\s+"
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
