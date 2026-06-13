# lex2md

Fetch EU legal documents from [EUR-Lex](https://eur-lex.europa.eu/) and convert them to clean, structured Markdown.

Given a CELEX identifier (e.g. `32024R1183`), lex2md fetches the official HTML, parses the legal structure — preamble, recitals, articles, chapters, annexes, footnotes, tables — and renders it as a navigable Markdown document with a table of contents, intra-document links, and nested point lists.

## Features

- **Structural parsing** — Extracts articles, paragraphs, numbered/lettered points, nested subpoints, chapters, sections, and annexes
- **Footnote resolution** — Converts EUR-Lex footnote markers to Markdown `[^id]` references with annex-level namespacing
- **Table handling** — Simple tables as Markdown, complex colspan/rowspan tables as clean HTML, point-like tables as flat lists
- **Navigation** — Auto-generated TOC with wikilinks between articles and annexes
- **Preamble splitting** — Separates institutional intro from numbered recitals
- **Dual output** — Markdown file or structured JSON to stdout
- **Multi-language** — Supports any EUR-Lex language code
- **Obsidian support** — Block links (`^id`), footnote namespacing, wikilink navigation, and semantic cross-reference resolution
- **Semantic link resolution** — Converts `Article 3(1)(a)` and `Annex IV, point 1` citations into internal links, with external-document exclusion
- **Local HTML mode** — Parse a locally saved HTML file instead of fetching from EUR-Lex
- **Dual-format parsing** — Handles both modern ELI-classed and legacy EUR-Lex HTML layouts

## Installation

```bash
pip install -r requirements.txt
```

Requires Python 3.12+.

## Usage

```bash
# Fetch and convert to Markdown
lex2md 32024R1183

# Specify language and output path
lex2md 32024R1183 --lang fr --output regulation.md

# Output as JSON (to stdout)
lex2md 32024R1183 --json

# Parse a local HTML file
lex2md 32024R1183 --local document.html

# Obsidian-flavored output (wikilinks + block IDs + semantic links)
lex2md 32024R1183 --obsidian
```

### CLI Options

| Flag | Description | Default |
|---|---|---|
| `celex` | CELEX document identifier (positional) | required |
| `-l`, `--lang` | Language code | `en` |
| `-o`, `--output` | Output file path | `<celex>.md` |
| `-j`, `--json` | Write JSON to stdout instead of Markdown | off |
| `--local` | Path to local HTML file (bypasses fetching) | off |
| `--obsidian` | Shorthand for `--links wikilinks --block-links --resolve-links` | off |
| `--links` | Internal cross-reference style: `markdown` or `wikilinks` | `markdown` |
| `--block-links` | Add Obsidian-compatible `^id` block IDs to paragraphs/points | off |
| `--resolve-links` | Convert semantic citations (e.g. `Article 3(1)(a)`) into internal links | off |

## Example Output

```markdown
# REGULATION (EU) 2024/1183

- CELEX: `32024R1183`
- Language: `en`

## Navigation

- [[#Article 1 - Subject matter]]
- [[#ANNEX I - RISK REGISTER]]

## Preamble

THE EUROPEAN PARLIAMENT AND THE COUNCIL [^1], ...

## Articles

### CHAPTER I - GENERAL PROVISIONS

#### Article 1 - Subject matter

1. This Regulation establishes a framework... ^article-1-1
   - (a) governance rules; ^article-1-1-a
   - (b) review procedures. ^article-1-1-b
```

## Project Structure

```
lex2md/
├── __init__.py          # Package exports
├── cli.py               # Argparse entry point (104 lines)
├── fetcher.py           # EUR-Lex HTTP client with WAF detection (56 lines)
├── models.py            # Dataclasses: EurLexDocument, Section, Paragraph, Point, Note, Recital (98 lines)
├── markdown.py          # EurLexDocument → Markdown string with semantic link resolution (847 lines)
└── parser/
    ├── __init__.py      # Re-exports parse_document_html, parse_eurlex_html
    ├── core.py          # HTML → EurLexDocument orchestration (657 lines)
    ├── text.py          # Text extraction, footnote markers, cleaning, slugify (122 lines)
    ├── tables.py        # Table → Markdown/HTML/points conversion (361 lines)
    └── points.py        # Paragraph & point extraction from body text (292 lines)
tests/
├── conftest.py               # Path setup
├── test_fetcher.py           # HTTP fetching, errors, WAF detection (5 tests)
├── test_parser.py            # Full HTML→dict parsing (18 tests)
├── test_parser_edge_cases.py # Empty HTML, broken footnotes, mismatched tables (3 tests)
├── test_markdown.py          # Markdown rendering: notes, paragraphs, points, subpoints (11 tests)
├── test_cli.py               # CLI output modes, local mode, error handling (6 tests)
├── test_integration.py       # Real HTML fixture parsing (1 gated test)
└── test_obsidian.py          # Obsidian features: block links, footnote namespacing, wikilinks, semantic links (30 tests)
```

## Architecture Map

### Data Flow

```
CLI (cli.py)
  │
  ├── --local mode ──► read HTML file
  └── remote mode ───► fetcher.py ──► EUR-Lex API
                          │
                     HTML string
                          │
                   parser/ (core → text → tables → points)
                          │
                   models.EurLexDocument
                     ┌────┴────┐
                     │         │
               markdown.py   document_to_dict()
                     │         │
               .md file    JSON stdout
```

### Module Responsibilities

| Module | Role | Key Public API |
|---|---|---|
| `cli.py` | CLI entry point, arg parsing, orchestration | `main()` |
| `fetcher.py` | HTTP client for EUR-Lex, WAF detection | `fetch_document_html(celex_id, language)` |
| `models.py` | Data layer — all dataclasses + serialization | `EurLexDocument`, `Section`, `Paragraph`, `Point`, `Note`, `Recital`, `document_to_dict()` |
| `parser/core.py` | Main parser — extracts title, preamble, articles, annexes, hierarchy, final provisions | `parse_document_html(html, celex, language)`, `parse_eurlex_html(html)` |
| `parser/text.py` | Text extraction, footnote marker handling, cleaning, slugify | `_extract_text_with_note_markers()`, `_replace_note_markers()`, `_clean_inline_text()`, `_clean_block_text()` |
| `parser/tables.py` | HTML table → Markdown/HTML/points; rowspan normalization | `_extract_markdown_table()`, `_extract_table_points()` |
| `parser/points.py` | Body text → Paragraph/Point decomposition | `_extract_article_paragraphs()`, `_extract_points()` |
| `markdown.py` | EurLexDocument → Markdown; link resolution, block IDs, footnote namespacing | `generate_markdown(document, *, links_style, add_block_links, resolve_semantic_links)` |

### Data Model

```
EurLexDocument
├── title: str
├── celex: str
├── language: str
├── preamble: str
├── preamble_intro: str
├── preamble_recitals: list[Recital]
│       ├── number: str
│       └── text: str
├── preamble_notes: list[Note]
├── articles: list[Section]
├── annexes: list[Section]
├── final_text: str
└── signature_lines: list[str]

Section (used for articles and annexes)
├── id: str                  # "Article 1" / "ANNEX I"
├── title: str               # "Subject matter" / "RISK REGISTER"
├── chapter_id: str          # "CHAPTER I"
├── chapter_title: str       # "GENERAL PROVISIONS"
├── section_id: str          # "SECTION 1"
├── section_title: str       # "General provisions"
├── body: str                # Raw text (unused when paragraphs are present)
├── paragraphs: list[Paragraph]
│       ├── number: str      # "1" / "" (unnumbered)
│       ├── text: str
│       └── points: list[Point]
│               ├── marker: str   # "(a)", "(1)", "-", "—"
│               ├── style: str    # "lower_alpha", "arabic", "dash", "lower_roman", "upper_alpha", "upper_roman", "other"
│               ├── text: str
│               └── subpoints: list[Point]  # Recursive nesting
└── notes: list[Note]
        ├── id: str
        └── text: str
```

### Parser Pipeline

1. **Title extraction** — `<h1 class="ti-main">` or legacy selectors
2. **Preamble** — `div#pbl_*` or legacy `Institutionquiagit` → `Formuledadoption` range
3. **Recital split** — `(N)` numbered recitals separated from institutional intro
4. **Article hierarchy** — Chapter/section metadata from `div#cpt_*` containers
5. **Article extraction** — `div.eli-subdivision#art_*` or legacy `p.Titrearticle`
6. **Paragraph/point decomposition** — Body text split by `N.` / `(N)` patterns; inline `(a)`, `(b)` point extraction; dash list extraction; table point extraction; nested subpoint extraction
7. **Final provisions** — `div.oj-final` + `div.oj-signatory`
8. **Annex extraction** — `div.eli-container#anx_*` with namespaced footnotes
9. **Footnote resolution** — `ntc→#ntr` link pattern; `[[FN:id]]` tokens → `[^id]` Markdown refs

### Markdown Rendering Pipeline

1. **Title + metadata** (CELEX, language)
2. **Navigation** — wikilinks-only `[[#heading]]` TOC
3. **Preamble** — footnote namespacing (`[^fn-id]` when block links active) + intra-links
4. **Articles** — chapter/section group headings → paragraph rendering → point/subpoint nested dash lists
5. **Final provisions + signatures**
6. **Annexes** — same structure as articles
7. **Semantic link resolution** — post-processes all text:
   - `Article 3` → `[[#Article 3|Article 3]]` or `[Article 3](#Article%203)`
   - `Article 3(1)(a)` → `[[#^article-3-1-a|Article 3(1)(a)]]` (with block links)
   - `Articles 5c(4) and 5e(2)` → two separate links
   - `Annex IV, point 1` → `[[#^annex-iv-1|Annex IV, point 1]]`
   - Excludes `Article X of Regulation/Directive...` (external references)

## Running Tests

```bash
python -m pytest tests/ -v
```

## Tooling

| Tool | Config | Details |
|---|---|---|
| ruff | `pyproject.toml` | target=py312, line-length=100, rules: E/W/F/I/UP/B/SIM/RUF |
| mypy | `pyproject.toml` | strict mode, python 3.12, ignore_missing_imports |
| pytest | `pyproject.toml` | testpaths=["tests"], with pytest-mock |
| uv | `pyproject.toml` | Package manager; dev deps: pytest, pytest-mock, ruff, mypy |
| hatchling | `pyproject.toml` | Build backend |

## License

BSL-1.1
