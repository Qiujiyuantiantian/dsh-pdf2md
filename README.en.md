# dsh-pdf2md

[中文说明](README.md)

A DSH skill that converts PDF, Word, PowerPoint, Excel and HTML into Markdown or
plain text — **and refuses scanned PDFs instead of writing an empty file.**

## Why this exists

The conversion libraries are not the problem. `pymupdf` and `markitdown` are both
excellent, and both will happily hand you a 0-byte `.md` for a scanned PDF,
because a scanned PDF has no text layer to extract. The next step in your
pipeline then consumes that empty file and produces confident nonsense.

This skill's contribution is the boundary, not the conversion:

- `probe` decides whether a text layer exists — read-only and fast
- a scanned document makes `convert` exit **2** and write **nothing**, with the
  next options spelled out
- `--format txt` always produces plain text; Markdown is never relabelled as `.txt`
- every command emits **exactly one** JSON document, so output is safe to parse

## Install

### As a DSH plugin (recommended)

```bash
dsh plugin --profile web add dsh-pdf2md
```

Desktop clients use their own profile name (the default is `desktop`):

```bash
dsh plugin --profile desktop add dsh-pdf2md
```

`dsh plugin add` installs the package into the profile **and registers it in `dsh.profile.bundles` automatically** — verified on a fresh profile, where one command added the entry. Restart DSH and `pdf2md` appears in the skill catalog.

Without the `dsh` command, `pnpm add dsh-pdf2md` plus a manual entry in the profile's `dsh.profile.bundles` works too.

### Python dependencies (required)

`scripts/pdf2md.py` needs Python 3.10+ plus:

```bash
<python> -m pip install -r skills/pdf2md/requirements.txt
```

Verify:

```bash
<python> skills/pdf2md/scripts/pdf2md.py doctor
```

If you do not know which interpreter to use, try in order: `$PDF2MD_PYTHON`,
`.venv/Scripts/python.exe`, `.venv/bin/python`, `python3`, `python` — the first
one that passes `doctor` is the right one.

## Usage

```bash
# inspect first (read-only)
python scripts/pdf2md.py probe report.pdf

# then convert
python scripts/pdf2md.py convert report.pdf --out ./out
python scripts/pdf2md.py convert report.pdf --engine structure --pages 1-6
python scripts/pdf2md.py convert ./docs --format txt --tables-csv
```

| Option | Meaning |
|---|---|
| `--out DIR` | output directory (default: alongside the source) |
| `--engine auto\|structure\|text` | engine selection |
| `--format md\|txt` | `txt` always means plain text |
| `--pages 1-3,7` | PDF page selection |
| `--tables-csv` | also export detected tables as CSV |

### The two engines

| | `structure` | `text` |
|---|---|---|
| Library | pymupdf4llm | markitdown |
| Heading levels | **preserved** | flattened |
| Formats | PDF only | PDF, DOCX, PPTX, XLSX, HTML, … |
| Best for | documents you will read or cite | feeding a model, mixed formats |

Measured on one real 24-page Chinese government form: `structure` over 6 pages →
3,708 characters with 10 heading lines; `text` over all 24 pages → 18,831
characters with 0 heading lines. Neither is better; they answer different
questions.

## Quality boundary

Do not promise what the format cannot deliver. See
[`skills/pdf2md/references/quality.md`](skills/pdf2md/references/quality.md):

- merged table cells: content survives, grouping does not
- two-column layouts may interleave
- equations become Unicode fragments, not LaTeX
- scanned pages: nothing at all until OCR runs — the companion [`dsh-scan2md`](https://github.com/Qiujiyuantiantian/dsh-scan2md) is the OCR step (resumable, page-addressable, with a quality report)

## Sandbox note

Child processes are frequently confined to the session workspace even when the
surrounding shell is not. A `PermissionError` outside the workspace is a sandbox
boundary, not a broken skill — write into the workspace instead.

## Development

```bash
python -m pytest tests -q          # 12 tests, fixtures generated at run time
node --check lib/startup.js        # bundle syntax
npm pack --dry-run                 # what would be published
```

CI runs the same three checks on Python 3.10 / 3.12 / 3.13 and Node 20.

## Publish

```bash
npm publish --access public
```

Fill in `author` and `repository` in `package.json` first — they are intentionally
left blank.

## Licence

MIT for this package. The conversion libraries keep their own terms: **PyMuPDF is
AGPL-3.0** (not bundled here — users install it), `markitdown` is MIT. If you wrap
this skill in a network service, review the AGPL obligations attached to PyMuPDF
before deploying.
