---
name: pdf2md
description: Convert PDF, Word, PowerPoint, Excel, HTML and similar documents into Markdown or plain text, preserving heading levels where the source allows it, and refusing scanned PDFs instead of writing empty output. Use when the user asks to 转成 markdown / 转成 txt / 提取文字 / 把文档转成可读文本 / 转成能喂给模型的格式, or when a downstream step (book distillation, RAG ingest, summarisation, search) needs text out of a PDF or Office file that only exists as a document.
metadata:
  version: "0.1.0"
---

# pdf2md

Turn a document into text a model can read, **and tell the truth about what the
conversion could and could not do.**

## The one rule

Never write an empty file and call it a conversion.

A scanned PDF has no text layer. Extraction returns nothing. Emitting a 0-byte
`.md` is worse than refusing, because the next step in the pipeline will happily
consume it and produce confident nonsense. `probe` exists so this cannot happen
silently; `convert` exits **2** with `needs_ocr` and writes no file.

## Step 1 — probe before converting

```bash
<python> scripts/pdf2md.py probe <file-or-directory>
```

This is cheap and read-only. It reports, per document: page count, characters per
page, whether a usable text layer exists, table and image counts, and a verdict
of `text` or `needs_ocr`.

Do this first for any PDF you have not seen before. Do not start with `convert`
and inspect the output afterwards.

## Step 2 — convert

```bash
<python> scripts/pdf2md.py convert <file-or-directory> [options]
```

| Option | Meaning |
|---|---|
| `--out DIR` | output directory (default: alongside the source) |
| `--engine auto\|structure\|text` | engine selection, see below |
| `--format md\|txt` | `md` keeps structure; `txt` is plain text, always |
| `--pages 1-3,7` | PDF page selection |
| `--tables-csv` | also export each detected table as its own CSV |

A directory input converts every supported file inside it.

**`--format txt` always produces plain text**, whatever `--engine` says — the
engine then only picks the reader. Do not promise Markdown structure in a `.txt`.

## Step 3 — choosing an engine

| | `structure` | `text` |
|---|---|---|
| Library | pymupdf4llm | markitdown |
| Keeps heading levels | **yes** | no |
| Formats | PDF only | PDF, DOCX, PPTX, XLSX, HTML, CSV, JSON, XML |
| Best for | documents you will read or cite | feeding a model, mixed formats |

`auto` probes first: PDFs with a text layer go to `structure`, everything else to
`text`. Override it when you know what the output is for.

Measured on one real 24-page Chinese government form: `structure` over 6 pages
produced 3 708 characters with 10 heading lines; `text` over all 24 pages produced
18 831 characters with 0 heading lines. Neither is "better" — they answer
different questions.

## When the verdict is `needs_ocr`

Say so, plainly, and offer the next step. Do not retry the same command, and do
not silently fall back to another engine hoping for text.

Legitimate next steps:

- read the pages with a vision model (works for a handful of pages; slow for a book)
- install an OCR pipeline (`tesseract` + language data, or `markitdown-ocr` with a
  vision-model client) and re-probe
- ask the user whether the document is worth OCR at all

## Finding a usable interpreter

The script needs Python 3.10+ with `pymupdf`. `pymupdf4llm` is needed for
`structure`, `markitdown` for non-PDF input and `--engine text`.

Try, in order, and use the first that passes `doctor`:

1. `$PDF2MD_PYTHON`
2. `.venv/Scripts/python.exe` or `.venv/bin/python` under the working directory
3. `python3`, then `python`

```bash
<python> scripts/pdf2md.py doctor
```

`doctor` prints the interpreter it is running under plus a per-dependency check,
and on failure prints the exact install command. Relay that command rather than
improvising a different one.

## Write output where it is writable

Child processes are frequently confined to the session workspace even when the
surrounding shell is not. If a write fails with `PermissionError` outside the
workspace, do not conclude the skill is broken — write into the workspace and say
where the file went.

## Report what happened

After converting, state: engine used, page range, character count, output path.
If `needs_ocr`, say which pages lack text and what the options are.

Read `references/quality.md` before promising anything about merged-cell tables,
multi-column layouts, or formulas.
