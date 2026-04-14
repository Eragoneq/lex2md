from __future__ import annotations

import re
from html import escape as html_escape

from bs4 import Tag

from lex2md.models import (
    Point,
)

POINT_MARKER_TOKEN = r"(?:\d+[a-zA-Z]?|[a-z]|[A-Z]|[ivxlcdm]{1,6}|[IVXLCDM]{1,6})"
from lex2md.parser.text import _clean_inline_text, _extract_text_with_note_markers, _has_class


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
    if (header_flags and header_flags[0]) or (_looks_like_header_row(rows[0]) and not _is_point_marker_cell(rows[0][0])):
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
