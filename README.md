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
- Optionally inlines footnotes into paragraph text
- Renders tables as plain text
- Splits large texts into parts by character count (~650K chars each)
- Exports to Markdown with YAML front matter

## Quickstart

**Requirements:** Python 3.9+

```bash
pip install beautifulsoup4 lxml
```

Download an HTML file from Project Gutenberg (e.g., [Ricardo's Principles](https://www.gutenberg.org/ebooks/33310)), then run:

```bash
python -m mnemos_pipeline.cli gutenberg/pg33310-images.html -o output --author david-ricardo --slug principles
```

This produces:
- `output/david-ricardo/principles/principles.json` — canonical JSON
- `output/david-ricardo/principles/principles.md` — Markdown

### Flags

| Flag | Description |
|------|-------------|
| `--author NAME` | Author folder name (required) |
| `--slug NAME` | Work folder/filename base (defaults to HTML file stem) |
| `-o DIR` | Root output directory (default: `output`) |
| `--max-chars N` | Part splitting threshold in characters (default: 650000) |
| `--no-footnotes` | Strip all footnote markers and text |
| `--no-markdown` | Skip Markdown export |

## Works in the library

| Author | Work | Source |
|--------|------|--------|
| Adam Smith | Theory of Moral Sentiments | [pg64457](https://www.gutenberg.org/ebooks/64457) |
| David Ricardo | Principles of Political Economy | [pg33310](https://www.gutenberg.org/ebooks/33310) |
| Edward Gibbon | Decline and Fall of the Roman Empire | [pg25717](https://www.gutenberg.org/ebooks/25717) |
| Ernest Hemingway | The Sun Also Rises | [pg67138](https://www.gutenberg.org/ebooks/67138) |
| Virginia Woolf | The Common Reader | [pg67363](https://www.gutenberg.org/ebooks/67363) |
| Virginia Woolf | Mrs. Dalloway | [pg71865](https://www.gutenberg.org/ebooks/71865) |

## Output structure

```
output/
  adam-smith/
    theory-of-moral-sentiments/
  david-ricardo/
    principles/
  edward-gibbon/
    decline-and-fall/
      decline-and-fall-part-1.json
      decline-and-fall-part-2.json
      ...
  ernest-hemingway/
    the-sun-also-rises/
  virginia-woolf/
    common-reader/
    mrs-dalloway/
```

Large texts are automatically split into parts at chapter boundaries so each file stays under the character limit.

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
gutenberg/      — source HTML files from Project Gutenberg
output/         — generated JSON and Markdown, organized by author/work
docs/
  gutenberg_pipeline_prd.md — product requirements document
reader.html     — browser-based validation reader
```

## License

This project is open source. Gutenberg texts are in the public domain.
