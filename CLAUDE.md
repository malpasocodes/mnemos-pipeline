# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Gutenberg Ingestion & Normalization Pipeline** — converts Project Gutenberg HTML files into structured JSON for a side-by-side reading and note-taking app. Annotations are handled in the app layer, not here.

## Running the Pipeline

```bash
pip3 install beautifulsoup4 lxml
python3 -m mnemos_pipeline.cli gutenberg/pg33310-images.html -o output --slug ricardo-principles
```

Flags: `--slug NAME` for output filename base (e.g. `gibbon-decline-and-fall`), `--no-markdown` to skip Markdown export, `-o DIR` for output directory, `--max-chars N` to control part splitting threshold in characters (default 650000), `--no-footnotes` to strip all footnote markers and text.

## Pipeline Architecture

Two-stage pipeline:

```
Local HTML file → Canonical JSON → Markdown (optional)
```

- **Stage 1 (`parser.py`):** HTML → Canonical JSON. Strips Gutenberg boilerplate (`#pg-header`, `#pg-footer`), detects chapters via `<h4>CHAPTER` pattern, segments paragraphs, strips page markers, inlines footnotes, renders tables as plain text, converts inline formatting to Markdown markers (`*italic*`, `**bold**`), assigns positional IDs.
- **Stage 2 (`exporter.py`):** Canonical JSON → Markdown. Renders chapters as `##` headings, paragraphs as body text, metadata as YAML front matter.

## Canonical Data Model

```json
{
  "meta": { "title": "string", "author": "string", "gutenberg_id": "string" },
  "chapters": [
    {
      "id": "ch-1",
      "title": "string | null",
      "paragraphs": [
        { "id": "ch-1/p-0", "text": "string" }
      ]
    }
  ]
}
```

**ID format:** Positional — `ch-{n}` for chapters, `ch-{n}/p-{m}` for paragraphs. Stable across re-runs given the same input. The reading app uses these to anchor annotations.

## Key Design Decisions

- Preface is included as `ch-0`; TOC, errata, index, and ads are excluded
- Footnotes are inlined into paragraph text as `[N] footnote text...`
- Drop caps are rendered as plain text (decorative bold stripped)
- Chapter detection fallback: entire body as single chapter with `title: null`
- Input is manually downloaded HTML (no URL fetching)
