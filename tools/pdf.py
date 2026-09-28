"""PDF tools -- the iLovePDF half, on qpdf / ghostscript / poppler."""
from __future__ import annotations

from pathlib import Path

from registry import Param, ToolError, py_module, run_cmd, tool

PRESETS = (
    ("screen", "Smallest (72 dpi)"),
    ("ebook", "Balanced (150 dpi)"),
    ("printer", "High quality (300 dpi)"),
    ("prepress", "Press quality (300 dpi, colour preserved)"),
)


def _out(outdir: Path, stem: str, ext: str) -> Path:
    return outdir / f"{stem}.{ext}"


@tool(id="pdf-merge", label="Merge", blurb="Join several PDFs into one, in the order dropped.",
      category="PDF", accepts=("pdf",), multi=True, engines=("qpdf",))
def merge(inputs, params, outdir):
    out = _out(outdir, "merged", "pdf")
    run_cmd(["qpdf", "--empty", "--pages", *inputs, "--", out])
    return [out]


@tool(id="pdf-split", label="Split", blurb="Burst into one file per page, or pull out a page range.",
      category="PDF", accepts=("pdf",), engines=("qpdf",),
      params=(
          Param("mode", "How", "select", "each",
                (("each", "One file per page"), ("range", "Keep only a page range"))),
          Param("ranges", "Pages", "text", "", placeholder="1-3,7,10-z",
                help="Used for 'keep only a range'. z means last page."),
      ))
def split(inputs, params, outdir):
    src = inputs[0]
    if params.get("mode") == "range":
        spec = (params.get("ranges") or "").strip()
        if not spec:
            raise ToolError("Give a page range, e.g. 1-3,7")
        out = _out(outdir, f"{src.stem}_p{spec.replace(',', '_')}", "pdf")
        run_cmd(["qpdf", src, "--pages", ".", spec, "--", out])
        return [out]
    run_cmd(["qpdf", "--split-pages", src, outdir / f"{src.stem}_page.pdf"])
    return sorted(outdir.glob(f"{src.stem}_page*.pdf"))


@tool(id="pdf-rotate", label="Rotate", blurb="Turn every page, or just the ones you name.",
      category="PDF", accepts=("pdf",), engines=("qpdf",),
      params=(
          Param("angle", "Turn by", "select", "90",
                (("90", "90 clockwise"), ("180", "180"), ("270", "90 anticlockwise"))),
          Param("pages", "Pages", "text", "1-z", placeholder="1-z", help="1-z is every page."),
      ))
def rotate(inputs, params, outdir):
    src = inputs[0]
    pages = (params.get("pages") or "1-z").strip()
    out = _out(outdir, f"{src.stem}_rotated", "pdf")
    run_cmd(["qpdf", src, f"--rotate=+{params.get('angle', '90')}:{pages}", "--", out])
    return [out]


@tool(id="pdf-compress", label="Compress", blurb="Shrink by downsampling images. Text stays vector.",
      category="PDF", accepts=("pdf",), engines=("ghostscript",),
      params=(Param("preset", "Target", "select", "ebook", PRESETS),))
def compress(inputs, params, outdir):
    src = inputs[0]
    out = _out(outdir, f"{src.stem}_compressed", "pdf")
    run_cmd([
        "gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.7",
        f"-dPDFSETTINGS=/{params.get('preset', 'ebook')}",
        "-dNOPAUSE", "-dQUIET", "-dBATCH", "-dDetectDuplicateImages=true",
        f"-sOutputFile={out}", str(src),
    ])
    if not out.exists():
        raise ToolError("Ghostscript produced no output")
    return [out]


@tool(id="pdf-protect", label="Protect", blurb="Encrypt with a password needed to open it.",
      category="PDF", accepts=("pdf",), engines=("qpdf",),
      params=(
          Param("password", "Password", "password", "", required=True),
          Param("allow_print", "Still allow printing", "bool", True),
      ))
def protect(inputs, params, outdir):
    src = inputs[0]
    pw = params.get("password") or ""
    if not pw:
        raise ToolError("A password is required")
    out = _out(outdir, f"{src.stem}_protected", "pdf")
    args = ["qpdf", "--encrypt", pw, pw, "256"]
    if not params.get("allow_print", True):
        args += ["--print=none"]
    args += ["--", str(src), str(out)]
    run_cmd(args)
    return [out]


@tool(id="pdf-unlock", label="Unlock", blurb="Strip the password from a PDF you can already open.",
      category="PDF", accepts=("pdf",), engines=("qpdf",),
      params=(Param("password", "Current password", "password", "",
                    help="Leave blank if it only has an owner password."),))
def unlock(inputs, params, outdir):
    src = inputs[0]
    out = _out(outdir, f"{src.stem}_unlocked", "pdf")
    args = ["qpdf", "--decrypt"]
    if params.get("password"):
        args.append(f"--password={params['password']}")
    args += [str(src), str(out)]
    run_cmd(args)
    return [out]


@tool(id="pdf-organize", label="Reorder pages", blurb="Keep, drop or reshuffle pages by number.",
      category="PDF", accepts=("pdf",), engines=("qpdf",),
      params=(Param("spec", "Page order", "text", "", required=True,
                    placeholder="1,5,2-4,z", help="Listed order is the new order."),))
def organize(inputs, params, outdir):
    src = inputs[0]
    spec = (params.get("spec") or "").strip()
    if not spec:
        raise ToolError("Give a page order, e.g. 1,5,2-4")
    out = _out(outdir, f"{src.stem}_organized", "pdf")
    run_cmd(["qpdf", src, "--pages", ".", spec, "--", out])
    return [out]


@tool(id="pdf-to-image", label="PDF to image", blurb="Render each page to PNG or JPG.",
      category="PDF", accepts=("pdf",), engines=("poppler",),
      params=(
          Param("format", "Format", "select", "png", (("png", "PNG"), ("jpeg", "JPG"))),
          Param("dpi", "Resolution", "number", 150, help="150 for screen, 300 for print."),
      ))
def pdf_to_image(inputs, params, outdir):
    src = inputs[0]
    fmt = params.get("format", "png")
    try:
        dpi = max(30, min(600, int(params.get("dpi") or 150)))
    except (TypeError, ValueError):
        dpi = 150
    run_cmd(["pdftoppm", f"-{fmt}", "-r", str(dpi), src, outdir / src.stem])
    made = sorted(p for p in outdir.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
    if not made:
        raise ToolError("No pages were rendered")
    return made


@tool(id="pdf-to-text", label="Extract text", blurb="Pull the text layer out as a .txt.",
      category="PDF", accepts=("pdf",), engines=("poppler",),
      params=(Param("layout", "Preserve layout", "bool", True),))
def pdf_to_text(inputs, params, outdir):
    src = inputs[0]
    out = _out(outdir, src.stem, "txt")
    args = ["pdftotext"]
    if params.get("layout", True):
        args.append("-layout")
    args += [str(src), str(out)]
    run_cmd(args)
    if out.stat().st_size == 0:
        raise ToolError("No text layer found -- this looks like a scan. Try OCR first.")
    return [out]


@tool(id="pdf-ocr", label="OCR", blurb="Add a searchable text layer to a scan.",
      category="PDF", accepts=("pdf",), engines=("ocrmypdf", "tesseract", "ghostscript"),
      params=(
          Param("language", "Language", "text", "eng", placeholder="eng",
                help="Tesseract code. eng+tam for two."),
          Param("force", "Redo pages that already have text", "bool", False),
          Param("deskew", "Straighten crooked scans", "bool", True),
          Param("pre_rotate", "Page orientation", "select", "auto",
                (("auto", "Detect automatically"), ("none", "Already upright"),
                 ("90", "Turn 90 clockwise first"), ("180", "Turn 180 first"),
                 ("270", "Turn 90 anticlockwise first")),
                help="Sideways scans OCR into gibberish. Detection needs clean text to work; "
                     "on a photographed or colour-heavy page, set the turn by hand."),
      ))
def ocr(inputs, params, outdir):
    src = inputs[0]
    out = _out(outdir, f"{src.stem}_ocr", "pdf")
    args = ["--language", (params.get("language") or "eng").strip()]
    args.append("--force-ocr" if params.get("force") else "--skip-text")
    if params.get("deskew"):
        args.append("--deskew")

    turn = str(params.get("pre_rotate", "auto"))
    source = src
    if turn in ("90", "180", "270"):
        # Tesseract's own orientation detection gives up on photographed pages
        # (it scores well under its confidence floor), so rotate first and let
        # it read a page that is already the right way up.
        scratch = outdir / "_tmp"
        scratch.mkdir(exist_ok=True)
        source = scratch / f"{src.stem}_turned.pdf"
        run_cmd(["qpdf", str(src), f"--rotate=+{turn}:1-z", "--", str(source)])
    elif turn == "auto":
        args += ["--rotate-pages", "--rotate-pages-threshold", "8"]

    run_cmd(py_module("ocrmypdf", *args, str(source), str(out)), timeout=1800)
    return [out]


@tool(id="pdf-to-docx", label="PDF to Word", blurb="Best-effort .docx. Simple layouts convert well; dense tables do not.",
      category="PDF", accepts=("pdf",), engines=("pdf2docx",))
def pdf_to_docx(inputs, params, outdir):
    from pdf2docx import Converter
    src = inputs[0]
    out = _out(outdir, src.stem, "docx")
    conv = Converter(str(src))
    try:
        conv.convert(str(out))
    except Exception as exc:
        raise ToolError(f"Layout reconstruction failed: {exc}")
    finally:
        conv.close()
    return [out]


@tool(id="pdf-watermark", label="Watermark", blurb="Stamp diagonal text across every page.",
      category="PDF", accepts=("pdf",), engines=("pypdf", "reportlab"),
      params=(
          Param("text", "Text", "text", "DRAFT", required=True),
          Param("opacity", "Opacity", "number", 15, help="Percent. 10-25 reads without hiding content."),
          Param("size", "Font size", "number", 60),
      ))
def watermark(inputs, params, outdir):
    return _stamp(inputs[0], params, outdir, mode="watermark")


@tool(id="pdf-page-numbers", label="Page numbers", blurb="Number the pages along the bottom.",
      category="PDF", accepts=("pdf",), engines=("pypdf", "reportlab"),
      params=(
          Param("position", "Position", "select", "bottom-center",
                (("bottom-center", "Bottom centre"), ("bottom-right", "Bottom right"),
                 ("bottom-left", "Bottom left"))),
          Param("start", "First page is number", "number", 1),
          Param("size", "Font size", "number", 11),
      ))
def page_numbers(inputs, params, outdir):
    return _stamp(inputs[0], params, outdir, mode="numbers")


def _stamp(src: Path, params: dict, outdir: Path, mode: str) -> list[Path]:
    """Overlay generated text onto each page. One reportlab canvas per page so
    the stamp lands correctly on mixed page sizes."""
    import io

    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.colors import Color
    from reportlab.pdfgen import canvas

    def num(key, fallback):
        try:
            return float(params.get(key) or fallback)
        except (TypeError, ValueError):
            return float(fallback)

    reader = PdfReader(str(src))
    writer = PdfWriter()
    size = num("size", 60 if mode == "watermark" else 11)
    start = int(num("start", 1))
    text = (params.get("text") or "DRAFT").strip()
    opacity = max(0.02, min(1.0, num("opacity", 15) / 100.0))
    position = params.get("position", "bottom-center")

    for index, page in enumerate(reader.pages):
        box = page.mediabox
        width, height = float(box.width), float(box.height)
        buf = io.BytesIO()
        pdf = canvas.Canvas(buf, pagesize=(width, height))
        if mode == "watermark":
            pdf.setFont("Helvetica-Bold", size)
            pdf.setFillColor(Color(0, 0, 0, alpha=opacity))
            pdf.saveState()
            pdf.translate(width / 2, height / 2)
            pdf.rotate(45)
            pdf.drawCentredString(0, 0, text)
            pdf.restoreState()
        else:
            pdf.setFont("Helvetica", size)
            pdf.setFillColor(Color(0, 0, 0, alpha=0.75))
            label = str(index + start)
            y = 24
            if position == "bottom-right":
                pdf.drawRightString(width - 40, y, label)
            elif position == "bottom-left":
                pdf.drawString(40, y, label)
            else:
                pdf.drawCentredString(width / 2, y, label)
        pdf.save()
        buf.seek(0)
        page.merge_page(PdfReader(buf).pages[0])
        writer.add_page(page)

    out = outdir / f"{src.stem}_{'watermarked' if mode == 'watermark' else 'numbered'}.pdf"
    with out.open("wb") as fh:
        writer.write(fh)
    return [out]


@tool(id="pdf-repair", label="Repair", blurb="Rebuild a PDF that other readers choke on.",
      category="PDF", accepts=("pdf",), engines=("qpdf",))
def repair(inputs, params, outdir):
    src = inputs[0]
    out = _out(outdir, f"{src.stem}_repaired", "pdf")
    try:
        run_cmd(["qpdf", "--decrypt", "--object-streams=disable", src, out])
    except ToolError:
        # qpdf refuses badly broken files that mutool will still salvage.
        run_cmd(["mutool", "clean", src, out])
    return [out]


@tool(id="pdf-to-pdfa", label="Convert to PDF/A", blurb="Archival format, for submissions that demand it.",
      category="PDF", accepts=("pdf",), engines=("ghostscript",))
def to_pdfa(inputs, params, outdir):
    src = inputs[0]
    out = _out(outdir, f"{src.stem}_pdfa", "pdf")
    run_cmd([
        "gs", "-dPDFA=2", "-dBATCH", "-dNOPAUSE", "-dQUIET",
        "-sColorConversionStrategy=UseDeviceIndependentColor",
        "-sDEVICE=pdfwrite", "-dPDFACompatibilityPolicy=1",
        f"-sOutputFile={out}", str(src),
    ])
    return [out]
