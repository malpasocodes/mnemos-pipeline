# Product Requirements Document (PRD)
## Project: Gutenberg Ingestion & Normalization Pipeline

---

## 1. Overview

A data transformation pipeline that converts Project Gutenberg HTML files into structured JSON suitable for a side-by-side reading and note-taking application.

The pipeline takes a locally downloaded Gutenberg HTML file and produces:
- **Canonical JSON** — the primary output, with stable paragraph-level IDs that the reading app uses to anchor annotations
- **Markdown** — optional secondary output for human inspection

---

## 2. Goals

- Convert Gutenberg HTML into clean, structured JSON with a consistent schema
- Segment text into chapters and paragraphs with stable, deterministic IDs
- Remove Gutenberg boilerplate (header, footer, license blocks)
- Normalize inconsistent whitespace, line breaks, and formatting
- Produce Markdown as an optional readable export

---

## 3. Non-Goals

- Automated retrieval of Gutenberg files (input is manual)
- Batch processing of multiple books
- Annotation, note-taking, or any app-layer concerns
- NLP enrichment, embeddings, or semantic analysis
- Support for non-Gutenberg sources
- Real-time processing
- Lossless HTML preservation

---

## 4. Pipeline

```
Local HTML file → Canonical JSON → Markdown (optional)
```

### Stage 1: HTML → Canonical JSON

**Input:** A Gutenberg HTML file on disk.

**Processing:**
1. Parse HTML and extract content elements
2. Detect and remove Gutenberg boilerplate (preamble, license, footer)
3. Identify chapter boundaries using heading heuristics
4. Segment content into paragraphs
5. Normalize whitespace and line breaks
6. Preserve inline emphasis (italic, bold) as Markdown-style markers in text
7. Assign stable positional IDs to chapters and paragraphs
8. Extract available metadata (title, author, Gutenberg ID)

**Output:** A single JSON file conforming to the canonical schema.

### Stage 2: Canonical JSON → Markdown

**Input:** Canonical JSON file.

**Processing:**
1. Render chapters as `##` headings
2. Render paragraphs as body text separated by blank lines
3. Include metadata as a YAML front matter block

**Output:** A single Markdown file.

---

## 5. Data Model

### Canonical JSON Schema

```json
{
  "meta": {
    "title": "string",
    "author": "string",
    "gutenberg_id": "string"
  },
  "chapters": [
    {
      "id": "ch-1",
      "title": "string | null",
      "paragraphs": [
        {
          "id": "ch-1/p-1",
          "text": "string"
        }
      ]
    }
  ]
}
```

**ID format:** Positional — `ch-{n}` for chapters, `ch-{n}/p-{m}` for paragraphs. These are stable across re-runs given the same input. The reading app uses these IDs to anchor annotations to specific paragraphs.

**Inline formatting:** Preserved in `text` as Markdown-style markers (`*italic*`, `**bold**`). This keeps the text field a simple string while retaining emphasis.

**Chapter detection fallback:** If chapter boundaries cannot be determined, the entire body is emitted as a single chapter with `"title": null`.

---

## 6. Non-Functional Requirements

- **Determinism:** Same input always produces the same output, byte-for-byte
- **Graceful degradation:** Malformed HTML should produce partial output with warnings, not crash
- **Inspectability:** JSON output should be human-readable (pretty-printed)

---

## 7. Validation Strategy

Select a small set of structurally diverse reference books:
- One with clear chapter headings (e.g., *The Wealth of Nations*)
- One with non-standard or absent chapter structure
- One with footnotes or inline references

Use these as golden-file regression tests: process each, verify output matches expected structure, and catch regressions on changes to parsing logic.

---

## 8. Decisions

| Question | Decision |
|---|---|
| Paragraph IDs: content-hash or positional? | **Positional** (`ch-1/p-3`). Human-readable, stable across normalization changes. |
| Inline formatting in canonical JSON? | **Preserved as Markdown markers** in the text string. |
| Footnotes? | **Deferred.** Handle if/when a specific book requires it. Not a first-pass concern. |
| Non-standard book structures? | **Single-chapter fallback** with `title: null`, flagged for manual review. |
| Two JSON stages or one? | **One.** Raw JSON adds complexity without value for this use case. |

---

End of Document
