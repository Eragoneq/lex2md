# lex2md

Fetch EU legal documents from [EUR-Lex](https://eur-lex.europa.eu/) and convert them to clean, structured Markdown.

Given a CELEX identifier (e.g. `32024R1183`), lex2md fetches the official HTML, parses the legal structure — preamble, recitals, articles, chapters, annexes, footnotes, tables — and renders it as a navigable Markdown document with a table of contents, intra-document links, and nested point lists.

## Features

- **Structural parsing** — Extracts articles, paragraphs, numbered/lettered points, nested subpoints, chapters, sections, and annexes
- **Footnote resolution** — Converts EUR-Lex footnote markers to Markdown `[^id]` references with annex-level namespacing
- **Table handling** — Simple tables as Markdown, complex colspan/rowspan tables as clean HTML
- **Navigation** — Auto-generated TOC with anchor links between articles and annexes
- **Preamble splitting** — Separates institutional intro from numbered recitals
- **Dual output** — Markdown file or structured JSON to stdout
- **Multi-language** — Supports any EUR-Lex language code

## Installation

```bash
pip install -r requirements.txt
```

Requires Python 3.12+.

## Usage

```bash
# Fetch and convert to Markdown
python cli.py 32024R1183

# Specify language and output path
python cli.py 32024R1183 --lang fr --output regulation.md

# Output as JSON (to stdout)
python cli.py 32024R1183 --json
```

### CLI Options

| Flag | Description | Default |
|---|---|---|
| `celex` | CELEX document identifier (positional) | required |
| `-l`, `--lang` | Language code | `en` |
| `-o`, `--output` | Output file path | `<celex>.md` |
| `-j`, `--json` | Write JSON to stdout instead of Markdown | off |

## Example Output

```markdown
# REGULATION (EU) 2024/1183

- CELEX: `32024R1183`
- Language: `en`

## Navigation

- [Article 1 - Subject matter](#article-1)
- [ANNEX I - RISK REGISTER](#annex-i)

## Preamble

THE EUROPEAN PARLIAMENT AND THE COUNCIL [^1], ...

## Articles

### CHAPTER I - GENERAL PROVISIONS

#### Article 1 - Subject matter

1. This Regulation establishes a framework...
   - (a) governance rules;
   - (b) review procedures.
```

## Project Structure

```
lex2md/
├── __init__.py    # Package exports
├── cli.py         # Argparse entry point
├── fetcher.py     # EUR-Lex HTTP client with WAF detection
├── models.py      # Dataclasses (EurLexDocument, Section, Paragraph, Point, ...)
├── parser.py      # HTML → EurLexDocument (BeautifulSoup)
└── markdown.py    # EurLexDocument → Markdown string
tests/
├── test_fetcher.py
├── test_parser.py
└── test_markdown.py
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## License

TBD
