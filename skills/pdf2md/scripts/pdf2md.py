#!/usr/bin/env python3
"""pdf2md — convert documents to Markdown or plain text, without lying about quality.

Two engines, chosen by what the document actually is:

  structure   pymupdf4llm — keeps heading levels, page-accurate, PDF only
  text        markitdown — broad format support (PDF/DOCX/PPTX/XLSX/HTML),
                           flattens structure, good for feeding LLMs

The point of this script is the boundary, not the conversion: a scanned PDF has
no text layer, and silently emitting an empty file is worse than refusing. So
`convert` probes first and exits 2 with `needs_ocr` instead of writing nothing.

Exit codes
  0  success
  2  needs OCR (document has no usable text layer)
  3  missing dependency
  4  bad input / nothing to do
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_NEEDS_OCR = 2
EXIT_MISSING_DEP = 3
EXIT_BAD_INPUT = 4

MARKDOWN_SUFFIXES = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".md", ".csv", ".json", ".xml", ".txt"}
PDF_SUFFIXES = {".pdf"}

# Below this many characters per page (median), a PDF is treated as scanned.
SCANNED_CHARS_PER_PAGE = 40


def _load_pymupdf():
    try:
        import pymupdf  # PyMuPDF >= 1.24
        return pymupdf
    except ImportError:
        pass
    try:
        import fitz  # legacy import name
        return fitz
    except ImportError:
        return None


def _require_pymupdf():
    module = _load_pymupdf()
    if module is None:
        print(
            "error: PyMuPDF is not installed for this interpreter.\n"
            f"  interpreter: {sys.executable}\n"
            "  fix: <same python> -m pip install pymupdf pymupdf4llm\n"
            "  fast mirror (CN): -i https://pypi.tuna.tsinghua.edu.cn/simple",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_MISSING_DEP)
    return module


def probe_pdf(path: Path) -> dict:
    """Structural facts about one PDF. Read-only, no engine beyond PyMuPDF."""
    pymupdf = _require_pymupdf()
    try:
        doc = pymupdf.open(str(path))
    except Exception as exc:  # noqa: BLE001 - surface the real reason
        return {"path": str(path), "ok": False, "error": f"{type(exc).__name__}: {exc}"}

    pages = []
    try:
        for index, page in enumerate(doc):
            try:
                text = page.get_text("text") or ""
            except Exception:
                text = ""
            tables = 0
            try:
                tables = len(page.find_tables().tables)
            except Exception:
                tables = 0
            try:
                images = len(page.get_images(full=True))
            except Exception:
                images = 0
            pages.append(
                {
                    "page": index + 1,
                    "chars": len(text.strip()),
                    "tables": tables,
                    "images": images,
                }
            )
        page_count = doc.page_count
    finally:
        doc.close()

    char_counts = sorted(p["chars"] for p in pages) or [0]
    median = char_counts[len(char_counts) // 2]
    total = sum(char_counts)
    has_text_layer = median >= SCANNED_CHARS_PER_PAGE

    return {
        "path": str(path),
        "ok": True,
        "pages": page_count,
        "total_chars": total,
        "median_chars_per_page": median,
        "has_text_layer": has_text_layer,
        "verdict": "text" if has_text_layer else "needs_ocr",
        "tables": sum(p["tables"] for p in pages),
        "images": sum(p["images"] for p in pages),
        "pages_detail": pages[:40],
    }


def _parse_pages(spec: str) -> list[int]:
    """'1-3,7' -> [0,1,2,6] (0-based)."""
    result: list[int] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start, _, end = chunk.partition("-")
            result.extend(range(int(start) - 1, int(end)))
        else:
            result.append(int(chunk) - 1)
    return sorted(set(result))


def convert_structure(path: Path, pages: list[int] | None) -> str:
    """Markdown that preserves heading levels. PDF only."""
    try:
        import pymupdf4llm
    except ImportError:
        print(
            "error: pymupdf4llm is not installed for this interpreter.\n"
            f"  fix: {sys.executable} -m pip install pymupdf4llm",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_MISSING_DEP)
    kwargs = {"pages": pages} if pages else {}
    return pymupdf4llm.to_markdown(str(path), **kwargs)


def convert_text(path: Path, plain: bool = False, pages: list[int] | None = None) -> str:
    """Flat text. `plain=True` uses PyMuPDF extraction for PDFs, else markitdown."""
    if plain and path.suffix.lower() in PDF_SUFFIXES:
        pymupdf = _require_pymupdf()
        doc = pymupdf.open(str(path))
        try:
            selected = [doc[i] for i in pages] if pages else list(doc)
            return "\n\n".join(page.get_text("text") or "" for page in selected).strip()
        finally:
            doc.close()

    try:
        from markitdown import MarkItDown
    except ImportError:
        print(
            "error: markitdown is not installed for this interpreter.\n"
            f"  fix: {sys.executable} -m pip install 'markitdown[pdf]'\n"
            "  (or use --engine structure for PDF input, which needs only pymupdf4llm)",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_MISSING_DEP)
    return MarkItDown().convert(str(path)).text_content


def convert_any(
    path: Path, engine: str, pages: list[int] | None, fmt: str
) -> tuple[str | None, str | None, dict | None]:
    """Return (body, engine_used, probe_info).

    A scanned PDF returns `(None, None, probe_info)` rather than printing a
    second JSON document: every CLI command emits exactly one JSON object on
    stdout, so consumers never have to split concatenated documents.

    Contract:
      --format txt   always yields plain text, whatever --engine says; the engine
                     then only selects the reader (PyMuPDF for PDF, markitdown
                     otherwise). Structure cannot survive a plain-text request.
      --engine auto  probes a PDF first and refuses scanned input.
    """
    suffix = path.suffix.lower()
    plain = fmt == "txt"

    # Refuse scanned PDFs before producing an empty file, unless the caller
    # explicitly asked for markitdown.
    if suffix in PDF_SUFFIXES and engine in ("auto", "structure"):
        info = probe_pdf(path)
        if not info.get("ok"):
            print(f"error: cannot open {path}: {info.get('error')}", file=sys.stderr)
            raise SystemExit(EXIT_BAD_INPUT)
        if info["verdict"] == "needs_ocr":
            return None, None, info

    if plain:
        return convert_text(path, plain=True, pages=pages), "plain", None

    if engine == "auto":
        engine = "structure" if suffix in PDF_SUFFIXES else "text"

    if engine == "structure":
        if suffix not in PDF_SUFFIXES:
            print(
                f"error: --engine structure only handles PDF; use --engine text for {suffix}",
                file=sys.stderr,
            )
            raise SystemExit(EXIT_BAD_INPUT)
        return convert_structure(path, pages), "structure", None

    if engine == "text":
        return convert_text(path, plain=False), "text", None

    print(f"error: unknown engine {engine!r}", file=sys.stderr)
    raise SystemExit(EXIT_BAD_INPUT)


def write_tables_csv(path: Path, out_dir: Path) -> list[str]:
    """Export every detected table as its own CSV. Best effort, never fatal."""
    pymupdf = _require_pymupdf()
    written: list[str] = []
    try:
        doc = pymupdf.open(str(path))
    except Exception:
        return written
    try:
        for index, page in enumerate(doc, start=1):
            try:
                tables = page.find_tables().tables
            except Exception:
                continue
            for number, table in enumerate(tables, start=1):
                try:
                    rows = table.extract()
                except Exception:
                    continue
                if not rows:
                    continue
                target = out_dir / f"{path.stem}.p{index}.t{number}.csv"
                with target.open("w", encoding="utf-8", newline="") as handle:
                    for row in rows:
                        cells = ["" if cell is None else str(cell).replace("\n", " ") for cell in row]
                        handle.write(",".join('"' + c.replace('"', '""') + '"' for c in cells) + "\n")
                written.append(str(target))
    finally:
        doc.close()
    return written


def collect_inputs(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(p for p in target.rglob("*") if p.is_file() and p.suffix.lower() in MARKDOWN_SUFFIXES)
    return []


def cmd_probe(args: argparse.Namespace) -> int:
    target = Path(args.path)
    if not target.exists():
        print(f"error: no such file or directory: {target}", file=sys.stderr)
        return EXIT_BAD_INPUT
    reports = []
    for path in collect_inputs(target):
        if path.suffix.lower() in PDF_SUFFIXES:
            reports.append(probe_pdf(path))
        else:
            reports.append({"path": str(path), "ok": True, "verdict": "text", "note": "non-PDF: text layer assumed"})
    print(json.dumps({"count": len(reports), "documents": reports}, ensure_ascii=True, indent=2))
    if not reports:
        return EXIT_BAD_INPUT
    return EXIT_OK


def cmd_convert(args: argparse.Namespace) -> int:
    target = Path(args.path)
    if not target.exists():
        print(f"error: no such file or directory: {target}", file=sys.stderr)
        return EXIT_BAD_INPUT

    inputs = collect_inputs(target)
    if not inputs:
        print(f"error: nothing convertible at {target}", file=sys.stderr)
        return EXIT_BAD_INPUT

    out_dir = Path(args.out) if args.out else (target if target.is_dir() else target.parent)
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = _parse_pages(args.pages) if args.pages else None

    results = []
    for path in inputs:
        record = {"source": str(path), "engine": None, "output": None, "chars": 0}
        body, engine, probe = convert_any(path, args.engine, pages, args.format)
        if body is None:
            record["error"] = "needs_ocr"
            record["probe"] = {
                key: probe.get(key) for key in ("pages", "total_chars", "median_chars_per_page", "tables", "images")
            } if probe else None
            record["hint"] = (
                "no text layer: this is a scanned/image PDF. "
                "Recognise it as scanned and offer OCR (vision model or tesseract) "
                "instead of writing an empty file."
            )
            results.append(record)
            continue

        suffix = ".txt" if args.format == "txt" else ".md"
        destination = out_dir / (path.stem + suffix)
        destination.write_text(body, encoding="utf-8")

        record.update({"engine": engine, "output": str(destination), "chars": len(body)})
        if args.tables_csv and path.suffix.lower() in PDF_SUFFIXES:
            csv_dir = out_dir / f"{path.stem}.tables"
            csv_dir.mkdir(parents=True, exist_ok=True)
            record["tables_csv"] = write_tables_csv(path, csv_dir)
        results.append(record)

    needs_ocr = [r for r in results if r.get("error") == "needs_ocr"]
    payload = {"converted": len(results) - len(needs_ocr), "needs_ocr": len(needs_ocr), "results": results}
    print(json.dumps(payload, ensure_ascii=True, indent=2))

    if needs_ocr and len(needs_ocr) == len(results):
        return EXIT_NEEDS_OCR
    return EXIT_OK


def cmd_doctor(_args: argparse.Namespace) -> int:
    checks = []
    pymupdf = _load_pymupdf()
    checks.append({"name": "pymupdf", "ok": pymupdf is not None, "detail": getattr(pymupdf, "__version__", None) if pymupdf else None})
    try:
        import pymupdf4llm
        checks.append({"name": "pymupdf4llm", "ok": True, "detail": getattr(pymupdf4llm, "__version__", "installed")})
    except ImportError:
        checks.append({"name": "pymupdf4llm", "ok": False, "detail": None})
    try:
        import markitdown
        checks.append({"name": "markitdown", "ok": True, "detail": getattr(markitdown, "__version__", "installed")})
    except ImportError:
        checks.append({"name": "markitdown", "ok": False, "detail": None})

    healthy = checks[0]["ok"]
    print(json.dumps({"interpreter": sys.executable, "healthy": healthy, "checks": checks}, ensure_ascii=True, indent=2))
    if not healthy:
        print(
            "fix: <interpreter> -m pip install pymupdf pymupdf4llm 'markitdown[pdf]'\n"
            "     (CN mirror: -i https://pypi.tuna.tsinghua.edu.cn/simple)",
            file=sys.stderr,
        )
        return EXIT_MISSING_DEP
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pdf2md", description="Convert documents to Markdown or text.")
    sub = parser.add_subparsers(dest="command", required=True)

    probe = sub.add_parser("probe", help="report whether documents have a usable text layer")
    probe.add_argument("path")
    probe.set_defaults(func=cmd_probe)

    convert = sub.add_parser("convert", help="convert files or a directory")
    convert.add_argument("path")
    convert.add_argument("--out", help="output directory (default: alongside the source)")
    convert.add_argument("--engine", choices=["auto", "structure", "text"], default="auto")
    convert.add_argument("--format", choices=["md", "txt"], default="md")
    convert.add_argument("--pages", help="PDF page selection, e.g. 1-3,7")
    convert.add_argument("--tables-csv", action="store_true", help="also export detected tables as CSV")
    convert.set_defaults(func=cmd_convert)

    doctor = sub.add_parser("doctor", help="check this interpreter's dependencies")
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
