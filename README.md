# lex2md

Fetch EU legal documents from [EUR-Lex](https://eur-lex.europa.eu/) and convert them to clean, structured Markdown.

Given a CELEX identifier (e.g. `32024R1183`), lex2md fetches the official HTML, parses the legal structure - preamble, recitals, articles, chapters, annexes, footnotes, tables. Then renders it as a navigable Markdown document with a table of contents, intra-document links, and nested point lists.

## Features

- **Structural parsing** - Extracts articles, paragraphs, numbered/lettered points, nested subpoints, chapters, sections, and annexes
- **Footnote resolution** - Converts EUR-Lex footnote markers to Markdown `[^id]` references with annex-level namespacing
- **Table handling** - Simple tables as Markdown, complex colspan/rowspan tables as clean HTML, point-like tables as flat lists
- **Navigation** - Auto-generated TOC with wikilinks between articles and annexes
- **Preamble splitting** - Separates institutional intro from numbered recitals
- **Dual output** - Markdown file or structured JSON to stdout
- **Multi-language** - Supports any EUR-Lex language code
- **Obsidian support** - Block links (`^id`), footnote namespacing, wikilink navigation, and semantic cross-reference resolution
- **Semantic link resolution** - Converts `Article 3(1)(a)` and `Annex IV, point 1` citations into internal links, with external-document exclusion
- **Local HTML mode** - Parse a locally saved HTML file instead of fetching from EUR-Lex
- **Dual-format parsing** - Handles both modern ELI-classed and legacy EUR-Lex HTML layouts

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

# Work in Progress

This is still a project mainly intended for personal use, as such it may contain bugs and not work on certain environments.
