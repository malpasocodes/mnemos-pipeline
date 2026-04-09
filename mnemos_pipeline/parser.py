"""Stage 1: HTML → Canonical JSON."""

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag


def parse_html(html_path: str) -> dict:
    """Parse a Gutenberg HTML file into canonical JSON."""
    html = Path(html_path).read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    meta = _extract_metadata(soup)
    footnotes = _extract_footnotes(soup)
    content_elements = _get_content_elements(soup)
    chapters = _segment_chapters(content_elements, footnotes)

    return {"meta": meta, "chapters": chapters}


def _extract_metadata(soup: BeautifulSoup) -> dict:
    """Extract title, author, and Gutenberg ID from the header."""
    meta = {"title": None, "author": None, "gutenberg_id": None}

    header = soup.find("section", id="pg-header")
    if not header:
        return meta

    machine = header.find("div", id="pg-machine-header")
    if machine:
        for p in machine.find_all("p"):
            strong = p.find("strong")
            if not strong:
                continue
            label = strong.get_text(strip=True).rstrip(":")
            # Text after the <strong> tag
            value = p.get_text(strip=True).replace(strong.get_text(strip=True), "", 1).strip(": ")
            if label == "Title":
                meta["title"] = value
            elif label == "Author":
                meta["author"] = value

    # Gutenberg ID from og:url or release date paragraph
    og_url = soup.find("meta", property="og:url")
    if og_url:
        m = re.search(r"/(\d+)/", og_url.get("content", ""))
        if m:
            meta["gutenberg_id"] = m.group(1)

    return meta


def _extract_footnotes(soup: BeautifulSoup) -> dict[str, str]:
    """Build a map of footnote number → footnote text."""
    footnotes = {}
    for div in soup.find_all("div", class_="footnote"):
        p = div.find("p")
        if not p:
            continue
        anchor = p.find("a", id=re.compile(r"^Footnote_\d+$"))
        if not anchor:
            continue
        num = anchor["id"].replace("Footnote_", "")
        # Get full text, then strip the leading [N] label
        text = _inline_text(p).strip()
        text = re.sub(r"^\s*\[\d+\]\s*", "", text)
        footnotes[num] = text
    return footnotes


def _get_content_elements(soup: BeautifulSoup) -> list[Tag]:
    """Return body elements between the Gutenberg header and footer,
    excluding boilerplate, TOC, errata, index, and ads."""
    body = soup.find("body")
    if not body:
        return []

    elements = []
    past_header = False
    past_title_page = False
    in_excluded_section = False

    for el in body.children:
        if not isinstance(el, Tag):
            continue

        # Skip header/footer boilerplate sections
        if el.get("class") and "pg-boilerplate" in el.get("class", []):
            if el.get("id") == "pg-header":
                past_header = True
            if el.get("id") == "pg-footer":
                break
            continue
        if el.get("id") == "pg-footer":
            break

        if not past_header:
            continue

        # Skip transcriber's note
        if el.get("class") and "box" in el.get("class", []):
            continue

        # Skip title page and TOC (before first content heading)
        _content_start_re = re.compile(
            r"^(PREFACE|CHAP\b|CHAPTER\b|INTRODUCTION|PART\b|SECTION\b)", re.IGNORECASE
        )
        if not past_title_page:
            text_check = el.get_text(strip=True)
            if el.name in ("h2", "h3", "h4") and _content_start_re.match(text_check):
                past_title_page = True
            elif el.name == "div" and el.get("class") and "chapter" in el.get("class", []):
                h_tag = el.find(["h2", "h3", "h4"])
                if h_tag and _content_start_re.match(h_tag.get_text(strip=True)):
                    past_title_page = True
                else:
                    continue
            else:
                continue

        # Stop at excluded back-matter sections
        heading_text = ""
        if el.name in ("h2", "h3", "h4", "h5"):
            heading_text = el.get_text(strip=True).upper()
        elif el.name == "div" and el.get("class") and "chapter" in el.get("class", []):
            h_tag = el.find(["h2", "h3", "h4"])
            if h_tag:
                heading_text = h_tag.get_text(strip=True).upper()
        if heading_text:
            if heading_text in ("CONTENTS.", "ERRATA.", "INDEX.", "NEW PUBLICATIONS."):
                in_excluded_section = True
                continue
            if heading_text == "THE END.":
                in_excluded_section = True
                continue
            if re.match(r"^(CHAPTER|CHAP\b|PREFACE|INTRODUCTION|PART\b|SECTION\b)", heading_text):
                in_excluded_section = False
            elif in_excluded_section:
                continue

        if in_excluded_section:
            continue

        # Skip footnote divs (handled separately)
        if el.get("class") and "footnote" in el.get("class", []):
            continue

        # Unwrap div containers that hold structural headings (Part, Section, Chapter)
        if el.name == "div":
            has_heading = el.find(["h2", "h3", "h4"])
            if has_heading:
                for child in el.children:
                    if isinstance(child, Tag):
                        elements.append(child)
                continue

        elements.append(el)

    return elements


def _heading_text(el: Tag) -> str:
    """Extract clean text from a heading element, preserving word boundaries."""
    text = el.get_text(" ", strip=True)
    # Clean up extra spaces before punctuation added by separator
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _segment_chapters(elements: list[Tag], footnotes: dict[str, str]) -> list[dict]:
    """Split elements into chapters based on CHAPTER/CHAP headings at h3 or h4 level."""
    chapters = []
    current_chapter = None
    # Track Part/Section context for books with hierarchical headings
    current_part = None
    current_section = None

    _chap_re = re.compile(r"^(CHAPTER|CHAP\b|PREFACE|INTRODUCTION)", re.IGNORECASE)

    for el in elements:
        # h2 can be a Part heading (context) or a Chapter/Preface heading
        if el.name == "h2":
            text = _heading_text(el)
            if re.match(r"^PART\b", text, re.IGNORECASE):
                current_part = text
                current_section = None
                continue
            if _chap_re.match(text):
                if current_chapter:
                    chapters.append(_finalize_chapter(current_chapter, footnotes))
                title_parts = []
                if current_part:
                    title_parts.append(current_part)
                if current_section:
                    title_parts.append(current_section)
                title_parts.append(text)
                current_chapter = {"title_parts": title_parts, "elements": []}
                continue

        # h3 can be a Section heading, Chapter heading, or subtitle
        if el.name == "h3":
            text = _heading_text(el)
            # If we just started a chapter (no content yet), treat h3 as subtitle
            if current_chapter and not current_chapter["elements"]:
                current_chapter["title_parts"].append(text)
                continue
            if re.match(r"^SECTION\b", text, re.IGNORECASE):
                current_section = text
                # Start a chapter for this section; if a CHAP heading follows,
                # it will finalize this one (possibly empty, which gets filtered out).
                if current_chapter:
                    chapters.append(_finalize_chapter(current_chapter, footnotes))
                title_parts = []
                if current_part:
                    title_parts.append(current_part)
                title_parts.append(current_section)
                current_chapter = {"title_parts": title_parts, "elements": []}
                continue
            if _chap_re.match(text):
                # Chapter at h3 level (e.g. Parts III-V of Theory of Moral Sentiments)
                if current_chapter:
                    chapters.append(_finalize_chapter(current_chapter, footnotes))
                title_parts = []
                if current_part:
                    title_parts.append(current_part)
                if current_section:
                    title_parts.append(current_section)
                title_parts.append(text)
                current_chapter = {"title_parts": title_parts, "elements": []}
                continue

        # Detect chapter or preface heading at h4 level
        if el.name == "h4":
            text = _heading_text(el)
            if _chap_re.match(text):
                if current_chapter:
                    chapters.append(_finalize_chapter(current_chapter, footnotes))
                title_parts = []
                if current_part:
                    title_parts.append(current_part)
                if current_section:
                    title_parts.append(current_section)
                title_parts.append(text)
                current_chapter = {"title_parts": title_parts, "elements": []}
                continue

        # Capture subtitle (h3/h5 near start of chapter, possibly after <hr>)
        if el.name in ("h3", "h5") and current_chapter and not current_chapter["elements"]:
            current_chapter["title_parts"].append(_heading_text(el))
            continue

        # Skip <hr> between chapter heading and subtitle
        if el.name == "hr" and current_chapter and not current_chapter["elements"]:
            continue

        if current_chapter is not None:
            current_chapter["elements"].append(el)

    if current_chapter:
        chapters.append(_finalize_chapter(current_chapter, footnotes))

    # Remove empty chapters (e.g. Section headings that were followed by CHAP sub-headings)
    chapters = [ch for ch in chapters if ch["paragraphs"]]

    # Assign IDs
    for i, ch in enumerate(chapters):
        ch["id"] = f"ch-{i}"
        for j, p in enumerate(ch["paragraphs"]):
            p["id"] = f"ch-{i}/p-{j}"

    return chapters


def _finalize_chapter(chapter_data: dict, footnotes: dict[str, str]) -> dict:
    """Convert raw chapter data into canonical form with paragraphs."""
    title_parts = [re.sub(r"\s+", " ", t.strip()) for t in chapter_data["title_parts"]]
    title = ". ".join(title_parts)
    # Clean up title: "CHAPTER I.. ON VALUE." → "Chapter I. On Value"
    title = re.sub(r"\.\.+", ".", title)

    paragraphs = []
    for el in chapter_data["elements"]:
        if el.name == "hr":
            continue
        if el.name == "p":
            # Skip page-number-only paragraphs
            if _is_pagenum_only(el):
                continue
            text = _inline_text(el)
            text = _attach_footnotes(text, footnotes)
            text = text.strip()
            if text:
                paragraphs.append({"text": text})
        elif el.name == "table":
            text = _render_table(el)
            if text.strip():
                paragraphs.append({"text": text.strip()})

    return {"title": title if title else None, "paragraphs": paragraphs}


def _is_pagenum_only(el: Tag) -> bool:
    """Check if a paragraph contains only a pagenum span."""
    children = [c for c in el.children if not (isinstance(c, NavigableString) and c.strip() == "")]
    if len(children) == 1 and isinstance(children[0], Tag):
        return children[0].get("class") and "pagenum" in children[0].get("class", [])
    return False


def _inline_text(el: Tag) -> str:
    """Extract text from an element, converting inline formatting to
    Markdown markers and stripping page numbers."""
    parts = []
    for child in el.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag):
            if child.get("class") and "pagenum" in child.get("class", []):
                continue
            if child.name == "i" or child.name == "em":
                inner = _inline_text(child)
                if inner.strip():
                    parts.append(f"*{inner}*")
            elif child.name == "b" or child.name == "strong":
                inner = _inline_text(child)
                if inner.strip():
                    parts.append(f"**{inner}**")
            elif child.name == "sup":
                parts.append(_inline_text(child))
            elif child.name == "br":
                parts.append(" ")
            elif child.name == "a" and "fnanchor" in " ".join(child.get("class", [])):
                # Footnote anchor — keep the reference number
                num = child.get_text(strip=True)
                parts.append(f"[^{num}]")
            elif child.name == "a":
                parts.append(_inline_text(child))
            elif child.name == "span":
                cls = " ".join(child.get("class", []))
                if "xhtml_big" in cls:
                    # Drop cap — extract plain text, skip bold/formatting
                    parts.append(child.get_text())
                elif "smcap" in cls:
                    parts.append(_inline_text(child))
                elif "label" in cls:
                    parts.append(_inline_text(child))
                else:
                    parts.append(_inline_text(child))
            else:
                parts.append(_inline_text(child))

    text = "".join(parts)
    # Collapse all whitespace (including newlines from HTML source) into single spaces
    text = re.sub(r"\s+", " ", text)
    return text


def _attach_footnotes(text: str, footnotes: dict[str, str]) -> str:
    """Replace footnote markers [^N] with inline footnote text."""
    def replacer(m):
        num = m.group(1)
        fn_text = footnotes.get(num)
        if fn_text:
            return f" [{num}] {fn_text}"
        return m.group(0)

    return re.sub(r"\[\^(\d+)\]", replacer, text)


def _render_table(table: Tag) -> str:
    """Render an HTML table as plain text, one row per line."""
    lines = []
    for row in table.find_all("tr"):
        cells = []
        for td in row.find_all(["td", "th"]):
            cell_text = _inline_text(td).strip()
            if cell_text:
                cells.append(cell_text)
        if cells:
            lines.append("  ".join(cells))
    return "\n".join(lines)


def write_json(data: dict, output_path: str) -> None:
    """Write canonical JSON to file."""
    Path(output_path).write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
