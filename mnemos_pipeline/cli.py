"""CLI entry point for the pipeline."""

import argparse
import sys
from pathlib import Path

from mnemos_pipeline.parser import parse_html, write_json
from mnemos_pipeline.exporter import write_markdown


def main():
    parser = argparse.ArgumentParser(
        description="Convert Gutenberg HTML to canonical JSON and Markdown."
    )
    parser.add_argument("html_file", help="Path to a Gutenberg HTML file")
    parser.add_argument(
        "-o", "--output-dir",
        default="output",
        help="Output directory (default: output)",
    )
    parser.add_argument(
        "--no-markdown",
        action="store_true",
        help="Skip Markdown export",
    )
    args = parser.parse_args()

    html_path = Path(args.html_file)
    if not html_path.exists():
        print(f"Error: {html_path} not found", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = html_path.stem
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"

    print(f"Parsing {html_path}...")
    data = parse_html(str(html_path))

    n_chapters = len(data["chapters"])
    n_paragraphs = sum(len(ch["paragraphs"]) for ch in data["chapters"])
    print(f"Found {n_chapters} chapters, {n_paragraphs} paragraphs")

    write_json(data, str(json_path))
    print(f"Wrote {json_path}")

    if not args.no_markdown:
        write_markdown(data, str(md_path))
        print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
