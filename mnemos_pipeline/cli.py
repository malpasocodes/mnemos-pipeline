"""CLI entry point for the pipeline."""

import argparse
import math
import sys
from pathlib import Path

from mnemos_pipeline.parser import parse_html, write_json
from mnemos_pipeline.exporter import write_markdown


def split_parts(data: dict, max_chapters: int) -> list[dict]:
    """Split parsed data into parts when chapter count exceeds max_chapters.

    Returns a list of data dicts. Each has the same meta (extended with
    part/total_parts) and a slice of the chapters array with global IDs
    preserved.  If the text fits in one part, returns it unchanged (no
    part/total_parts fields added).
    """
    chapters = data["chapters"]
    if len(chapters) <= max_chapters:
        return [data]

    total_parts = math.ceil(len(chapters) / max_chapters)
    parts = []
    for i in range(total_parts):
        start = i * max_chapters
        end = start + max_chapters
        part_meta = {**data["meta"], "part": i + 1, "total_parts": total_parts}
        parts.append({"meta": part_meta, "chapters": chapters[start:end]})
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
        "--max-chapters",
        type=int,
        default=75,
        help="Max chapters per output file; larger texts are split into parts (default: 75)",
    )
    args = parser.parse_args()

    html_path = Path(args.html_file)
    if not html_path.exists():
        print(f"Error: {html_path} not found", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = html_path.stem

    print(f"Parsing {html_path}...")
    data = parse_html(str(html_path))

    n_chapters = len(data["chapters"])
    n_paragraphs = sum(len(ch["paragraphs"]) for ch in data["chapters"])
    print(f"Found {n_chapters} chapters, {n_paragraphs} paragraphs")

    parts = split_parts(data, args.max_chapters)

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
        print(f"Split into {len(parts)} parts ({args.max_chapters} chapters each)")


if __name__ == "__main__":
    main()
