from __future__ import annotations

import argparse
import json
import logging
import sys

from .fetcher import EurLexFetcherError, fetch_document_html
from .markdown import generate_markdown
from .models import document_to_dict
from .parser import parse_document_html


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch EUR-Lex documents and convert to Markdown or JSON."
    )
    parser.add_argument("celex", help="CELEX ID (for example: 32024R1183).")
    parser.add_argument(
        "-l", "--lang", default="en", help="Language code (default: en)."
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output markdown file path (default: <celex>.md).",
    )
    parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Write normalized JSON to stdout.",
    )
    parser.add_argument(
        "--local",
        help="Path to local HTML file to parse (bypasses fetching).",
    )

    args = parser.parse_args()

    log_level = logging.ERROR if args.json else logging.INFO
    logging.basicConfig(level=log_level, format="%(message)s", stream=sys.stderr)
    logger = logging.getLogger("lex2md")

    try:
        if args.local:
            logger.info(f"Reading local document {args.local}...")
            with open(args.local, encoding="utf-8") as f:
                html = f.read()
        else:
            logger.info(f"Fetching document {args.celex} in {args.lang}...")
            html = fetch_document_html(args.celex, args.lang)

        document = parse_document_html(html, celex=args.celex, language=args.lang)

        if args.json:
            print(json.dumps(document_to_dict(document), indent=2, ensure_ascii=True))
            return

        markdown = generate_markdown(document)
        output_path = args.output or f"{args.celex}.md"
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(markdown)
        logger.info(f"Wrote {output_path}")
    except EurLexFetcherError as exc:
        logger.error(f"Error fetching document: {exc}")
        raise SystemExit(1) from exc
    except Exception as exc:  # pragma: no cover
        logger.error(f"Unexpected error: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
