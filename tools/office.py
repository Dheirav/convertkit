"""Office and markup -- LibreOffice headless, and pandoc for the text formats."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from registry import Param, ToolError, run_cmd, tool, which_office

OFFICE_TARGETS = (
    ("pdf", "PDF"), ("docx", "Word (.docx)"), ("odt", "OpenDocument (.odt)"),
    ("rtf", "Rich text (.rtf)"), ("txt", "Plain text"),
    ("xlsx", "Excel (.xlsx)"), ("csv", "CSV"),
    ("pptx", "PowerPoint (.pptx)"), ("html", "HTML"),
)
MARKUP_TARGETS = (
    ("pdf", "PDF"), ("docx", "Word (.docx)"), ("html", "HTML"),
    ("md", "Markdown"), ("epub", "EPUB"), ("rst", "reStructuredText"),
    ("tex", "LaTeX"), ("txt", "Plain text"),
)


def _soffice(src: Path, target: str, outdir: Path) -> Path:
    """Each run gets its own profile dir -- LibreOffice silently no-ops if a
    second headless instance shares one."""
    profile = outdir / f"_lo_{uuid.uuid4().hex[:8]}"
    run_cmd([
        which_office(), "--headless", "--norestore",
        f"-env:UserInstallation=file://{profile}",
        "--convert-to", target, "--outdir", str(outdir), str(src),
    ], timeout=600)
    shutil.rmtree(profile, ignore_errors=True)
    made = outdir / f"{src.stem}.{target.split(':')[0]}"
    if not made.exists():
        raise ToolError(f"LibreOffice did not produce a .{target} -- the source may be unsupported")
    return made


@tool(id="office-to-pdf", label="Office to PDF", blurb="Word, Excel, PowerPoint and OpenDocument, rendered by LibreOffice.",
      category="Documents", accepts=("office",), engines=("libreoffice",))
def office_to_pdf(inputs, params, outdir):
    return [_soffice(inputs[0], "pdf", outdir)]


@tool(id="office-convert", label="Convert document", blurb="Between any two office formats.",
      category="Documents", accepts=("office",), engines=("libreoffice",),
      params=(Param("target", "To", "select", "pdf", OFFICE_TARGETS),))
def office_convert(inputs, params, outdir):
    target = params.get("target", "pdf")
    if target not in {t[0] for t in OFFICE_TARGETS}:
        raise ToolError("Unsupported target format")
    return [_soffice(inputs[0], target, outdir)]


@tool(id="markup-convert", label="Convert text format", blurb="Markdown, HTML, LaTeX, EPUB, docx -- via pandoc.",
      category="Documents", accepts=("markup",), engines=("pandoc",),
      params=(Param("target", "To", "select", "pdf", MARKUP_TARGETS),))
def markup_convert(inputs, params, outdir):
    src = inputs[0]
    target = params.get("target", "pdf")
    if target not in {t[0] for t in MARKUP_TARGETS}:
        raise ToolError("Unsupported target format")
    out = outdir / f"{src.stem}.{target}"
    args = ["pandoc", str(src), "-o", str(out)]
    if target == "pdf":
        # wkhtmltopdf-free path: pandoc needs a LaTeX engine otherwise.
        args += ["--pdf-engine=weasyprint"] if shutil.which("weasyprint") else []
    try:
        run_cmd(args, timeout=600)
    except ToolError as exc:
        if target == "pdf":
            raise ToolError(
                f"{exc}\n\nPDF output needs a LaTeX engine: sudo apt install texlive-xetex")
        raise
    return [out]
