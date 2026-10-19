"""Black-box tests for the pdf2md CLI and bundle manifest.

Everything here goes through the command line, the way an agent would use it.
Fixtures are generated at test time, so the repository holds no binary files.

Run:  python -m pytest tests -q
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "pdf2md" / "scripts" / "pdf2md.py"
MANIFEST = ROOT / "skills" / "pdf2md" / "SKILL.md"

pymupdf = pytest.importorskip("pymupdf", reason="PyMuPDF is required to generate fixtures")
yaml = pytest.importorskip("yaml", reason="PyYAML is required for the manifest checks")


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd) if cwd else None,
        timeout=600,
    )


@pytest.fixture
def text_pdf(tmp_path: Path) -> Path:
    """Two pages with a usable text layer."""
    doc = pymupdf.open()
    for index in range(2):
        page = doc.new_page()
        page.insert_textbox(
            pymupdf.Rect(72, 90, 520, 130), f"Section {index + 1}", fontsize=20
        )
        page.insert_textbox(
            pymupdf.Rect(72, 150, 520, 400),
            "The quick brown fox jumps over the lazy dog. " * 8,
            fontsize=11,
        )
    target = tmp_path / "text.pdf"
    doc.save(str(target))
    doc.close()
    return target


@pytest.fixture
def scanned_pdf(tmp_path: Path) -> Path:
    """A page rendered to an image and repacked: no text layer at all."""
    source = pymupdf.open()
    page = source.new_page()
    page.insert_text((72, 120), "Scanned page content", fontsize=18)
    png = tmp_path / "page.png"
    page.get_pixmap(dpi=100).save(str(png))

    images_only = pymupdf.open()
    fresh = images_only.new_page(width=page.rect.width, height=page.rect.height)
    fresh.insert_image(fresh.rect, filename=str(png))
    target = tmp_path / "scanned.pdf"
    images_only.save(str(target))
    images_only.close()
    source.close()
    return target


# --- doctor -----------------------------------------------------------------

def test_doctor_reports_healthy() -> None:
    result = run("doctor")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["healthy"] is True
    names = {check["name"] for check in payload["checks"]}
    assert {"pymupdf", "pymupdf4llm", "markitdown"} <= names


# --- probe ------------------------------------------------------------------

def test_probe_detects_text_layer(text_pdf: Path) -> None:
    result = run("probe", str(text_pdf))
    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)["documents"][0]
    assert document["pages"] == 2
    assert document["has_text_layer"] is True
    assert document["verdict"] == "text"


def test_probe_detects_scanned_document(scanned_pdf: Path) -> None:
    result = run("probe", str(scanned_pdf))
    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)["documents"][0]
    assert document["verdict"] == "needs_ocr"
    assert document["has_text_layer"] is False


# --- convert ----------------------------------------------------------------

def test_convert_writes_markdown(text_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = run("convert", str(text_pdf), "--out", str(out))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["converted"] == 1

    written = out / "text.md"
    assert written.is_file()
    assert len(written.read_text(encoding="utf-8")) > 100


def test_convert_refuses_scanned_without_writing(scanned_pdf: Path, tmp_path: Path) -> None:
    """The core promise: exit 2, one JSON document, and no file left behind."""
    out = tmp_path / "out"
    result = run("convert", str(scanned_pdf), "--out", str(out))
    assert result.returncode == 2
    payload = json.loads(result.stdout)  # exactly one document on stdout
    assert payload["needs_ocr"] == 1
    record = payload["results"][0]
    assert record["error"] == "needs_ocr"
    assert record["probe"]["total_chars"] == 0
    assert not out.exists() or list(out.rglob("*.md")) == []


def test_txt_output_is_plain_text(text_pdf: Path, tmp_path: Path) -> None:
    """--format txt must never emit Markdown, whatever the engine."""
    out = tmp_path / "out"
    result = run("convert", str(text_pdf), "--out", str(out), "--format", "txt")
    assert result.returncode == 0, result.stderr

    body = (out / "text.txt").read_text(encoding="utf-8")
    assert body.strip()
    assert not any(line.startswith("#") for line in body.splitlines())
    assert "|" not in body


def test_page_selection_limits_output(text_pdf: Path, tmp_path: Path) -> None:
    both = tmp_path / "both"
    one = tmp_path / "one"
    assert run("convert", str(text_pdf), "--out", str(both), "--format", "txt").returncode == 0
    assert run("convert", str(text_pdf), "--out", str(one), "--format", "txt", "--pages", "1").returncode == 0
    assert len((one / "text.txt").read_text(encoding="utf-8")) < len(
        (both / "text.txt").read_text(encoding="utf-8")
    )


def test_directory_input_converts_only_convertible(
    text_pdf: Path, scanned_pdf: Path, tmp_path: Path
) -> None:
    source = tmp_path / "batch"
    source.mkdir()
    (source / "text.pdf").write_bytes(text_pdf.read_bytes())
    (source / "scanned.pdf").write_bytes(scanned_pdf.read_bytes())
    (source / "notes.xyz").write_text("not a document", encoding="utf-8")

    out = tmp_path / "batch_out"
    result = run("convert", str(source), "--out", str(out))
    # One succeeds, one needs OCR: partial success is exit 0, with both reported.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["converted"] == 1
    assert payload["needs_ocr"] == 1
    assert [p.name for p in out.glob("*.md")] == ["text.md"]


def test_missing_input_exits_4(tmp_path: Path) -> None:
    result = run("convert", str(tmp_path / "does-not-exist.pdf"))
    assert result.returncode == 4


# --- bundle manifest --------------------------------------------------------

def test_cordis_patch_is_an_insert_row() -> None:
    data = yaml.safe_load((ROOT / "cordis.patch.yml").read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) == 1
    rows = data[0]["insert"]
    assert rows[0]["name"] == "dsh-pdf2md/startup"
    assert "skills" in rows[0]["inject"]


def test_package_json_declares_the_bundle() -> None:
    manifest = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert manifest["dsh"]["bundle"]["patch"] == "./cordis.patch.yml"
    assert manifest["files"] == sorted(manifest["files"]) or "skills" in manifest["files"]
    assert manifest["license"] == "MIT"


def test_skill_frontmatter_is_usable() -> None:
    text = MANIFEST.read_text(encoding="utf-8")
    assert text.startswith("---")
    block = text.split("---", 2)[1]
    fields = dict(
        line.split(":", 1) for line in block.splitlines() if ":" in line and not line.startswith(" ")
    )
    assert fields["name"].strip() == "pdf2md"
    description = fields["description"].strip()
    assert len(description) > 100
    # Trigger coverage: Chinese and English wording both present.
    assert "markdown" in description and "转成" in description
