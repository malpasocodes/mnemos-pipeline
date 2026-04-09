# mnemos-pipeline

A data transformation pipeline that converts [Project Gutenberg](https://www.gutenberg.org/) HTML files into structured JSON with stable paragraph-level IDs, suitable for reading and annotation applications.

## What it does

```
Gutenberg HTML → Canonical JSON → Markdown (optional)
```

- Strips Gutenberg boilerplate (header, footer, license)
- Detects chapters and segments text into paragraphs
- Assigns stable positional IDs (`ch-1/p-3`) for anchoring annotations
- Preserves inline emphasis as Markdown markers (`*italic*`, `**bold**`)
- Inlines footnotes into paragraph text
- Renders tables as plain text
- Exports to Markdown with YAML front matter

## Quickstart

**Requirements:** Python 3.9+

```bash
pip install beautifulsoup4 lxml
```

Download an HTML file from Project Gutenberg (e.g., [Ricardo's Principles](https://www.gutenberg.org/ebooks/33310)), then run:

```bash
python -m mnemos_pipeline.cli gutenberg/pg33310-images.html -o output
```

This produces:
- `output/pg33310-images.json` — canonical JSON
- `output/pg33310-images.md` — Markdown

Use `--no-markdown` to skip Markdown export.

## Output format

```json
{
  "meta": {
    "title": "On The Principles of Political Economy, and Taxation",
    "author": "David Ricardo",
    "gutenberg_id": "33310"
  },
  "chapters": [
    {
      "id": "ch-0",
      "title": "PREFACE.",
      "paragraphs": [
        {
          "id": "ch-0/p-0",
          "text": "The produce of the earth..."
        }
      ]
    }
  ]
}
```

Paragraph IDs are positional and deterministic — the same input always produces the same output.

## Validating output

Open `reader.html` in a browser and drag the JSON file onto it. This renders the full text with chapter navigation and paragraph IDs for visual inspection.

## Project structure

```
mnemos_pipeline/
  cli.py        — CLI entry point
  parser.py     — HTML → canonical JSON (Stage 1)
  exporter.py   — canonical JSON → Markdown (Stage 2)
docs/
  gutenberg_pipeline_prd.md — product requirements document
reader.html     — browser-based validation reader
```

## License

This project is open source. Gutenberg texts are in the public domain.
