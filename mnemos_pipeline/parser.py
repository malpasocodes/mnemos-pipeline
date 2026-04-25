"""Stage 1: HTML → Canonical JSON."""

import copy
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup, Comment, NavigableString, Tag


def parse_html(html_path: str, *, no_footnotes: bool = False) -> dict:
    """Parse a Gutenberg HTML file into canonical JSON."""
    html = Path(html_path).read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    meta = _extract_metadata(soup)
    footnotes = {} if no_footnotes else _extract_footnotes(soup)
    content_elements = _get_content_elements(soup)
    chapters = _segment_chapters(content_elements, footnotes)

    if no_footnotes:
        # Strip any remaining footnote markers [^key]
        for ch in chapters:
            for p in ch["paragraphs"]:
                p["text"] = re.sub(r"\s*\[\^[^\]]+\]", "", p["text"]).strip()

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
        anchor = p.find("a", id=re.compile(r"^Footnote_\d+(_\d+)?$"))
        if not anchor:
            continue
        fn_key = anchor["id"].replace("Footnote_", "")
        # Get full text, then strip the leading [N] label
        text = _inline_text(p).strip()
        text = re.sub(r"^\s*\[\d+\]\s*", "", text)
        footnotes[fn_key] = text

    # Thoreau-style: <p class="footnote"> with <a id="Footnote_N">
    for p in soup.find_all("p", class_="footnote"):
        anchor = p.find("a", id=re.compile(r"^Footnote_\d+(_\d+)?$"))
        if not anchor:
            continue
        fn_key = anchor["id"].replace("Footnote_", "")
        if fn_key in footnotes:
            continue
        text = _inline_text(p).strip()
        text = re.sub(r"^\s*\[\d+\]\s*", "", text)
        if text:
            footnotes[fn_key] = text

    # Gibbon-style: <p class="foot"> with <a class="pginternal" href="#linknoteref-...">
    for p in soup.find_all("p", class_="foot"):
        a = p.find("a", class_="pginternal")
        if not a:
            continue
        href = a.get("href", "")
        m = re.match(r"#linknoteref-(.+)", href)
        if not m:
            continue
        fn_key = m.group(1)
        text = _inline_text(p).strip()
        # Strip leading "101 (return) [ ..." pattern
        text = re.sub(r"^\S+\s*\(return\)\s*", "", text)
        text = text.strip()
        if text.startswith("["):
            text = text[1:].strip()
        if text.endswith("]"):
            text = text[:-1].strip()
        if text:
            footnotes[fn_key] = text

    return footnotes


def _get_content_elements(soup: BeautifulSoup) -> list[Tag]:
    """Return body elements between the Gutenberg header and footer,
    excluding boilerplate, TOC, errata, index, and ads."""
    body = soup.find("body")
    if not body:
        return []

    _content_start_re = re.compile(
        r"^(PREFACE|CHAP\b|CHAPTER|INTRODUCTION|PART\b|SECTION\b)", re.IGNORECASE
    )

    # Pre-scan: does the body contain an explicit <h*> content heading? If so,
    # the bare-<p> title-page fallback must not fire — otherwise title-page
    # imprint paragraphs (e.g. Locke's "REPRINTED, THE SIXTH TIME...") get
    # mistaken for body. Works that rely on the bare-<p> fallback either have
    # no chapter headings at all (Mrs Dalloway) or use plain-<p> headings
    # (Emerson's Nature) — neither of those leaves an <h*> match here.
    has_explicit_content_heading = any(
        h.name in ("h1", "h2", "h3", "h4")
        and (_content_start_re.match(h.get_text(strip=True)) or _has_anchor_id(h))
        for h in body.find_all(["h1", "h2", "h3", "h4"])
    )

    elements = []
    past_header = False
    past_title_page = False
    in_excluded_section = False
    pending_anchor_id = None

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
        if el.get("class") and ("box" in el.get("class", []) or "mynote" in el.get("class", [])):
            continue

        # Anchor-only <p> (e.g. <p><a id="link..."></a></p>) — Gutenberg uses
        # this to place a link target before a heading rather than as a child
        # of it. Capture the id, skip the <p>, and attach the id to the next
        # heading so existing essay-collection logic recognizes it.
        if el.name == "p" and _is_anchor_only_p(el):
            anchor = el.find("a", id=True)
            if anchor:
                pending_anchor_id = anchor["id"]
            continue
        if pending_anchor_id and el.name in ("h1", "h2", "h3", "h4"):
            if not el.get("id") and not _has_anchor_id(el):
                el["id"] = pending_anchor_id
            pending_anchor_id = None

        # Skip title page and TOC (before first content heading)
        if not past_title_page:
            text_check = el.get_text(strip=True)
            if el.name in ("h1", "h2", "h3", "h4") and _content_start_re.match(text_check):
                past_title_page = True
            elif el.name in ("h2", "h3", "h4") and (_has_anchor_id(el) or el.get("id")):
                # Essay collections: h2 with anchor child or own id marks content start
                past_title_page = True
            elif el.name == "div":
                h_tag = el.find(["h1", "h2", "h3", "h4"])
                if h_tag and _content_start_re.match(h_tag.get_text(strip=True)):
                    past_title_page = True
                elif h_tag and (_has_anchor_id(h_tag) or h_tag.get("id")):
                    # Essay collection wrapped in <div class="chapter"> (Thoreau)
                    past_title_page = True
                elif el.get("class") and "chapter" in el.get("class", []):
                    continue
                else:
                    continue
            # No heading found yet — if this is a plain <p>, assume we're
            # past front matter (novels with no chapter headings, or works
            # using plain-<p> headings like Emerson's Nature). Suppressed when
            # the document has an explicit <h*> content heading further down,
            # otherwise title-page imprint paragraphs would be captured.
            elif el.name == "p" and not el.get("class") and not has_explicit_content_heading:
                past_title_page = True
            else:
                continue

        # Stop at excluded back-matter sections
        heading_text = ""
        if el.name in ("h1", "h2", "h3", "h4", "h5"):
            heading_text = el.get_text(strip=True).upper()
        elif el.name == "div":
            h_tag = el.find(["h1", "h2", "h3", "h4"])
            if h_tag:
                heading_text = h_tag.get_text(strip=True).upper()
        if heading_text:
            bare = heading_text.rstrip(".").strip()
            if bare in ("CONTENTS", "ERRATA", "INDEX", "NEW PUBLICATIONS",
                        "ILLUSTRATIONS", "FOOTNOTES"):
                in_excluded_section = True
                continue
            if bare == "THE END" or re.match(r"^TRANSCRIBER", bare):
                in_excluded_section = True
                continue
            is_start = bool(re.match(r"^(CHAPTER|CHAP\b|PREFACE|INTRODUCTION|PART\b|SECTION\b)", heading_text))
            if not is_start and el.name in ("h1", "h2", "h3", "h4"):
                if _has_anchor_id(el) or el.get("id"):
                    is_start = True
            if not is_start and el.name == "div":
                h_inner = el.find(["h1", "h2", "h3", "h4"])
                if h_inner and (_has_anchor_id(h_inner) or h_inner.get("id")):
                    is_start = True
            if is_start:
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
            has_heading = el.find(["h1", "h2", "h3", "h4"])
            if has_heading:
                for child in el.children:
                    if isinstance(child, Tag):
                        elements.append(child)
                continue

        elements.append(el)

    return elements


def _has_anchor_id(el: Tag) -> bool:
    """Check if an element contains an <a> child with an id attribute."""
    a_tag = el.find("a", id=True)
    return a_tag is not None


def _is_anchor_only_p(el: Tag) -> bool:
    """True if `el` is a <p> whose only meaningful content is one <a id="...">.
    Whitespace, <br>, and HTML comments don't count. Used to detect Gutenberg
    chapter-anchor paragraphs that precede the actual heading."""
    has_anchor = False
    for child in el.children:
        if isinstance(child, Comment):
            continue
        if isinstance(child, NavigableString):
            if child.strip():
                return False
            continue
        if isinstance(child, Tag):
            if child.name == "br":
                continue
            if child.name == "a" and child.get("id"):
                if _inline_text(child).strip():
                    return False
                if has_anchor:
                    return False
                has_anchor = True
                continue
            return False
    return has_anchor


def _heading_text(el: Tag) -> str:
    """Extract clean text from a heading element, preserving word boundaries."""
    # Remove footnote anchors before extracting text
    el_copy = copy.copy(el)
    for a in el_copy.find_all("a", class_="fnanchor"):
        a.decompose()
    for a in el_copy.find_all("a", id=re.compile(r"^FNanchor")):
        a.decompose()
    text = el_copy.get_text(" ", strip=True)
    # Clean up extra spaces before punctuation added by separator
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_plain_p_heading(text: str) -> bool:
    """True if `text` looks like a chapter heading rendered as a plain <p>:
    short, all-caps letters, ending with a period."""
    if not text or len(text) > 40 or not text.endswith("."):
        return False
    body = text.rstrip(".")
    if not body:
        return False
    has_letter = False
    for ch in body:
        if ch.isalpha():
            has_letter = True
            if not ch.isupper():
                return False
    return has_letter


def _segment_chapters(elements: list[Tag], footnotes: dict[str, str]) -> list[dict]:
    """Split elements into chapters based on CHAPTER/CHAP headings at h3 or h4 level."""
    chapters = []
    current_chapter = None
    # Track Part/Section context for books with hierarchical headings
    current_part = None
    current_section = None

    _chap_re = re.compile(r"^(CHAPTER|CHAP\b|PREFACE|INTRODUCTION)", re.IGNORECASE)
    _roman_re = re.compile(r"^(I{1,3}|IV|V|VI{0,3}|IX|X)$")
    # Track essay group name and roman numeral sub-sections for essay collections
    current_essay_group = None
    pending_roman = None

    for el in elements:
        # h1 can be a Chapter heading (e.g. Hemingway)
        if el.name == "h1":
            text = _heading_text(el)
            if _chap_re.match(text):
                if current_chapter:
                    chapters.append(_finalize_chapter(current_chapter, footnotes))
                title_parts = []
                if current_part:
                    title_parts.append(current_part)
                title_parts.append(text)
                current_chapter = {"title_parts": title_parts, "elements": []}
                continue

        # h2 can be a Part heading (context) or a Chapter/Preface heading
        if el.name == "h2":
            text = _heading_text(el)
            if re.match(r"^PART\b", text, re.IGNORECASE):
                current_part = text
                current_section = None
                continue
            # Bare roman numeral sub-section (e.g. "I", "II") — store as prefix
            if _roman_re.match(text):
                # First roman numeral after an essay → remember the parent name
                if current_essay_group is None and current_chapter and current_chapter["title_parts"]:
                    current_essay_group = current_chapter["title_parts"][-1]
                pending_roman = text
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
                pending_roman = None
                current_essay_group = None
                current_chapter = {"title_parts": title_parts, "elements": []}
                continue
            # Essay collections: h2 with <a id="..."> or direct id= starts a new essay/chapter
            if _has_anchor_id(el) or el.get("id"):
                if current_chapter:
                    chapters.append(_finalize_chapter(current_chapter, footnotes))
                title_parts = []
                if pending_roman:
                    # Sub-section: prepend parent essay name and roman numeral
                    if current_essay_group:
                        title_parts.append(current_essay_group)
                    title_parts.append(pending_roman)
                    pending_roman = None
                else:
                    # Standalone essay — clear essay group context
                    current_essay_group = None
                title_parts.append(text)
                # subtitled=True protects against an h5 sub-section marker
                # (Johnson's act/scene labels) being absorbed as subtitle. A
                # following h3 without id (e.g. the date line under each
                # presidential inaugural, Du Bois's APPENDIX subtitles) is
                # still absorbed by the h3-specific catcher below.
                current_chapter = {"title_parts": title_parts, "elements": [], "subtitled": True}
                continue

        # h3 can be a Section heading, Chapter heading, or subtitle
        if el.name == "h3":
            text = _heading_text(el)
            # h3 with anchor/id starts a new essay-style sub-chapter (Thoreau appendix,
            # Johnson's play notes). Placed before the subtitle rule so each anchored h3
            # finalizes the prior chapter rather than being swallowed as a subtitle.
            if _has_anchor_id(el) or el.get("id"):
                if current_chapter:
                    chapters.append(_finalize_chapter(current_chapter, footnotes))
                title_parts = []
                if current_part:
                    title_parts.append(current_part)
                if current_section:
                    title_parts.append(current_section)
                title_parts.append(text)
                current_chapter = {"title_parts": title_parts, "elements": [], "subtitled": True}
                continue
            # If we just started a chapter (no content yet), treat h3 as subtitle
            if current_chapter and not current_chapter["elements"] and not current_chapter.get("subtitled"):
                current_chapter["title_parts"].append(text)
                current_chapter["subtitled"] = True
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

        # Capture subtitle near start of chapter (possibly after <hr>).
        # - h3: absorb unconditionally. The chapter-starting branches that
        #   set subtitled=True (h2 with id) are followed either by an h3
        #   with its own id (handled in the h3 branch above as a sub-chapter
        #   start) or by a plain h3 we want as subtitle.
        # - h5: only when subtitled=False, since Johnson uses h5 for act/
        #   scene sub-section markers under h2-with-id chapters where we
        #   want it rendered as a bold paragraph instead.
        if el.name == "h3" and current_chapter and not current_chapter["elements"]:
            current_chapter["title_parts"].append(_heading_text(el))
            current_chapter["subtitled"] = True
            continue
        if el.name == "h5" and current_chapter and not current_chapter["elements"] and not current_chapter.get("subtitled"):
            current_chapter["title_parts"].append(_heading_text(el))
            current_chapter["subtitled"] = True
            continue

        # Plain-<p> all-caps heading (e.g. Emerson's Nature uses "<p>CHAPTER I.</p>"
        # and "<p>NATURE.</p>" as paired chapter + subtitle instead of <h*> tags)
        if el.name == "p" and not el.get("class"):
            text = _inline_text(el).strip()
            if _is_plain_p_heading(text):
                if current_chapter and not current_chapter["elements"]:
                    current_chapter["title_parts"].append(text)
                    continue
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

        # Skip <hr> between chapter heading and subtitle
        if el.name == "hr" and current_chapter and not current_chapter["elements"]:
            continue

        if current_chapter is None:
            # No chapter heading seen yet — start a default chapter (e.g.
            # stream-of-consciousness novels with no chapter divisions)
            current_chapter = {"title_parts": [], "elements": []}
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
            # Skip footnote paragraphs (Gibbon-style)
            if el.get("class") and "foot" in el.get("class", []):
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
        elif el.name == "h5":
            # Preserve h5 sub-headings (e.g. Johnson's act labels) as bold paragraphs
            text = _inline_text(el).strip()
            if text:
                paragraphs.append({"text": f"**{text}**"})

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
        if isinstance(child, Comment):
            continue
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
                # Footnote anchor — extract key from href (#Footnote_N or #Footnote_N_N)
                href = child.get("href", "")
                fn_key = href.replace("#Footnote_", "")
                if fn_key:
                    parts.append(f"[^{fn_key}]")
            elif child.name == "a" and child.get("href", "").startswith("#linknote-") and "linknoteref" not in child.get("href", ""):
                # Gibbon-style footnote ref — extract key from href (#linknote-N.M)
                fn_key = child["href"].replace("#linknote-", "")
                parts.append(f"[^{fn_key}]")
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
    """Replace footnote markers [^KEY] with inline footnote text."""
    def replacer(m):
        fn_key = m.group(1)
        fn_text = footnotes.get(fn_key)
        if fn_text:
            # Display the trailing number for readability
            # e.g., "1_1" → "1", "1.101" → "101"
            display_num = fn_key.rsplit("_", 1)[-1] if "_" in fn_key else fn_key
            if "." in display_num:
                display_num = display_num.rsplit(".", 1)[-1]
            return f" [{display_num}] {fn_text}"
        return m.group(0)

    return re.sub(r"\[\^([^\]]+)\]", replacer, text)


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
