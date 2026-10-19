# Conversion quality: what survives and what does not

Measured on real documents, not estimated. Treat this as the boundary of what you
may promise.

## Text-layer PDFs

Survives well:

- paragraph text, in reading order for single-column layouts
- heading levels (`structure` engine only — `text` flattens everything)
- page boundaries, via `--pages`
- simple tables, as Markdown pipe tables

Degrades:

- **merged cells.** A form with a merged first column converts to a table with
  leading empty cells: the merge has no Markdown representation. The content is
  present; the layout is not. Do not describe such an output as "the table".
- **multi-column layouts.** Two-column academic papers may interleave the
  columns. `pdf_scan`-style column counts are a signal; verify before quoting.
- **footnotes** may land mid-paragraph.
- **equations** become Unicode fragments or vanish; they are not LaTeX.
- **headers/footers/page numbers** repeat on every page.

## Scanned / image-only PDFs

Nothing survives. `probe` reports `needs_ocr` and `convert` exits 2 without
writing a file. This is deliberate.

OCR is a separate decision with its own costs: a vision model is accurate but slow
and per-page; `tesseract` is fast but distinctly worse on Chinese; neither
reconstructs layout.

## Office documents

`markitdown` handles DOCX/PPTX/XLSX by reading their XML parts. Headings from Word
styles are lost in the same way as PDF `text` mode. Embedded images are not
described unless an OCR plugin is installed.

## Honest phrasing

Prefer:

> converted 24 pages, 18 831 characters, tables flattened to pipes; merged cells
> lost their grouping

Over:

> converted successfully

The second sentence is true and useless.
