# AGENTS.md

## Quick Commands

```bash
uv run lex2md <CELEX>              # Run CLI via uv
uv run lex2md <CELEX> --obsidian   # Obsidian output (wikilinks + block IDs + semantic links)
uv run lex2md <CELEX> --json       # JSON to stdout
uv run lex2md <CELEX> --local f.html  # Parse local HTML

python -m pytest tests/ -v         # Run all tests
uv run ruff check .                # Lint
uv run ruff format .               # Format
uv run mypy lex2md/                # Typecheck (strict mode)
```

Order: `ruff check -> ruff format -> mypy -> pytest`

## Architecture

Single Python package, no monorepo. Entry point: `lex2md.cli:main`.

```
cli.py -> fetcher.py (or --local) -> parser/core.py -> models.EurLexDocument -> markdown.py or document_to_dict()
```

Parser handles two EUR-Lex HTML formats: modern ELI-classed (`div.eli-subdivision`, `div.eli-container`) and legacy (`p.Titrearticle`, `div#pbl_*`).

Key modules:
- `parser/core.py` — main HTML→EurLexDocument orchestration
- `parser/points.py` — body text→Paragraph/Point decomposition (numbered, lettered, dash lists, nested)
- `parser/tables.py` — table→Markdown/HTML/points conversion with rowspan normalization
- `markdown.py` — document→Markdown with semantic link resolution, footnote namespacing, block IDs
- `models.py` — all dataclasses (EurLexDocument, Section, Paragraph, Point, Note, Recital)

## Testing

- Fixtures: `tests/fixtures/` contains real EUR-Lex HTML (`32016R0679.html` = GDPR, `32024R1183.html`)
- `test_integration.py` silently skips if fixtures dir is empty (no failure)
- `test_obsidian.py` is the largest suite (~30 tests) — block links, footnote namespacing, wikilinks, semantic links
- `conftest.py` adds project root to sys.path (needed for imports)

## Tooling

- Package manager: `uv` (dev deps in `pyproject.toml`)
- Build backend: `hatchling`
- Ruff: py312, line-length=100, rules E/W/F/I/UP/B/SIM/RUF
- Mypy: strict mode, python 3.12, ignore_missing_imports
- No CI, no pre-commit config

## Notes

- Root `output_*.md` and `session-*.md` files are conversion artifacts, not source — ignore
- `--obsidian` is shorthand for `--links wikilinks --block-links --resolve-links`
- Semantic link resolution excludes external references like "Article X of Regulation..."
