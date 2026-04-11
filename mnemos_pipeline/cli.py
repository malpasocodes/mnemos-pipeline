"""CLI entry point for the pipeline."""

import argparse
import sys
from pathlib import Path

from mnemos_pipeline.parser import parse_html, write_json
from mnemos_pipeline.exporter import write_markdown


def split_parts(data: dict, max_paragraphs: int) -> list[dict]:
    """Split parsed data into parts at chapter boundaries when total
    paragraph count exceeds max_paragraphs.

    Returns a list of data dicts. Each has the same meta (extended with
    part/total_parts) and a slice of the chapters array with global IDs
    preserved.  If the text fits in one part, returns it unchanged (no
    part/total_parts fields added).
    """
    chapters = data["chapters"]
    total_paras = sum(len(ch["paragraphs"]) for ch in chapters)
    if total_paras <= max_paragraphs:
        return [data]

    # Greedily pack chapters into parts without exceeding max_paragraphs
    parts_chapters = []
    current_part = []
    current_count = 0

    for ch in chapters:
        ch_paras = len(ch["paragraphs"])
        if current_part and current_count + ch_paras > max_paragraphs:
            parts_chapters.append(current_part)
            current_part = []
            current_count = 0
        current_part.append(ch)
        current_count += ch_paras

    if current_part:
        parts_chapters.append(current_part)

    total_parts = len(parts_chapters)
    parts = []
    for i, chs in enumerate(parts_chapters):
        part_meta = {**data["meta"], "part": i + 1, "total_parts": total_parts}
        parts.append({"meta": part_meta, "chapters": chs})
    return parts


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
    parser.add_argument(
        "--max-paragraphs",
        type=int,
        default=1500,
        help="Max paragraphs per output file; larger texts are split into parts (default: 1500)",
    )
    parser.add_argument(
        "--no-footnotes",
        action="store_true",
        help="Strip footnote markers and discard footnote text",
    )
    parser.add_argument(
        "--slug",
        help="Base filename for output (e.g. 'gibbon-decline-and-fall'); defaults to HTML file stem",
    )
    args = parser.parse_args()

    html_path = Path(args.html_file)
    if not html_path.exists():
        print(f"Error: {html_path} not found", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = args.slug or html_path.stem

    print(f"Parsing {html_path}...")
    data = parse_html(str(html_path), no_footnotes=args.no_footnotes)

    n_chapters = len(data["chapters"])
    n_paragraphs = sum(len(ch["paragraphs"]) for ch in data["chapters"])
    print(f"Found {n_chapters} chapters, {n_paragraphs} paragraphs")

    parts = split_parts(data, args.max_paragraphs)

    for part_data in parts:
        part_num = part_data["meta"].get("part")
        if part_num is not None:
            suffix = f"-part-{part_num}"
        else:
            suffix = ""

        json_path = out_dir / f"{stem}{suffix}.json"
        write_json(part_data, str(json_path))
        print(f"Wrote {json_path}")

        if not args.no_markdown:
            md_path = out_dir / f"{stem}{suffix}.md"
            write_markdown(part_data, str(md_path))
            print(f"Wrote {md_path}")

    if len(parts) > 1:
        print(f"Split into {len(parts)} parts (max {args.max_paragraphs} paragraphs each)")


if __name__ == "__main__":
    main()
