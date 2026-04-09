"""Stage 2: Canonical JSON → Markdown."""

from pathlib import Path


def to_markdown(data: dict) -> str:
    """Convert canonical JSON to Markdown with YAML front matter."""
    lines = []

    # YAML front matter
    meta = data.get("meta", {})
    lines.append("---")
    if meta.get("title"):
        lines.append(f"title: \"{meta['title']}\"")
    if meta.get("author"):
        lines.append(f"author: \"{meta['author']}\"")
    if meta.get("gutenberg_id"):
        lines.append(f"gutenberg_id: \"{meta['gutenberg_id']}\"")
    lines.append("---")
    lines.append("")

    for chapter in data.get("chapters", []):
        title = chapter.get("title") or "Untitled"
        lines.append(f"## {title}")
        lines.append("")

        for para in chapter.get("paragraphs", []):
            lines.append(para["text"])
            lines.append("")

    return "\n".join(lines)


def write_markdown(data: dict, output_path: str) -> None:
    """Write Markdown to file."""
    Path(output_path).write_text(to_markdown(data), encoding="utf-8")
