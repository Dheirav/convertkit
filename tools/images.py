"""Image tools -- Pillow does the work; img2pdf handles the lossless PDF path."""
from __future__ import annotations

from pathlib import Path

from registry import Param, ToolError, run_cmd, tool

IMAGE_FORMATS = (
    ("png", "PNG"), ("jpeg", "JPG"), ("webp", "WebP"),
    ("tiff", "TIFF"), ("bmp", "BMP"), ("gif", "GIF"),
)
_EXT = {"jpeg": "jpg", "tiff": "tif"}


def _ext(fmt: str) -> str:
    return _EXT.get(fmt, fmt)


@tool(id="img-to-pdf", label="Images to PDF", blurb="One page per image, no re-encoding of JPGs.",
      category="Image", accepts=("image",), multi=True, engines=("img2pdf", "pillow"),
      params=(
          Param("page", "Page size", "select", "fit",
                (("fit", "Match each image"), ("a4", "A4 portrait"), ("letter", "US Letter"))),
      ))
def images_to_pdf(inputs, params, outdir):
    import img2pdf
    from PIL import Image

    prepared: list[str] = []
    scratch = outdir / "_prep"
    scratch.mkdir(exist_ok=True)
    for src in inputs:
        with Image.open(src) as im:
            # img2pdf refuses alpha and palette images; flatten onto white.
            if im.mode in ("RGBA", "LA", "P"):
                flat = Image.new("RGB", im.size, "white")
                rgba = im.convert("RGBA")
                flat.paste(rgba, mask=rgba.split()[-1])
                tmp = scratch / f"{src.stem}.jpg"
                flat.save(tmp, "JPEG", quality=92)
                prepared.append(str(tmp))
            else:
                prepared.append(str(src))

    layout = None
    if params.get("page") in ("a4", "letter"):
        size = (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297)) if params["page"] == "a4" \
            else (img2pdf.in_to_pt(8.5), img2pdf.in_to_pt(11))
        layout = img2pdf.get_layout_fun(size)

    out = outdir / ("images.pdf" if len(inputs) > 1 else f"{inputs[0].stem}.pdf")
    # Phone photos routinely carry an out-of-range EXIF orientation (0 is not a
    # legal value); ifvalid honours a sane tag and ignores a broken one instead
    # of refusing the whole job.
    opts = {"rotation": img2pdf.Rotation.ifvalid}
    if layout:
        opts["layout_fun"] = layout
    with out.open("wb") as fh:
        fh.write(img2pdf.convert(prepared, **opts))
    return [out]


@tool(id="img-convert", label="Convert format", blurb="PNG, JPG, WebP, TIFF, BMP, GIF.",
      category="Image", accepts=("image",), engines=("pillow",),
      params=(
          Param("format", "To", "select", "png", IMAGE_FORMATS),
          Param("quality", "Quality", "number", 90, help="JPG and WebP only. 1-100."),
      ))
def img_convert(inputs, params, outdir):
    from PIL import Image

    fmt = params.get("format", "png")
    try:
        quality = max(1, min(100, int(params.get("quality") or 90)))
    except (TypeError, ValueError):
        quality = 90

    made = []
    for src in inputs:
        out = outdir / f"{src.stem}.{_ext(fmt)}"
        with Image.open(src) as im:
            if fmt in ("jpeg", "bmp") and im.mode in ("RGBA", "LA", "P"):
                flat = Image.new("RGB", im.size, "white")
                rgba = im.convert("RGBA")
                flat.paste(rgba, mask=rgba.split()[-1])
                im = flat
            elif im.mode == "P" and fmt != "gif":
                im = im.convert("RGBA")
            opts = {"quality": quality} if fmt in ("jpeg", "webp") else {}
            im.save(out, fmt.upper(), **opts)
        made.append(out)
    return made


@tool(id="img-resize", label="Resize", blurb="Scale by percentage, or bound the long edge.",
      category="Image", accepts=("image",), engines=("pillow",),
      params=(
          Param("mode", "How", "select", "percent",
                (("percent", "Percentage of original"), ("max", "Fit inside a box"))),
          Param("value", "Amount", "number", 50,
                help="Percent, or the longest edge in pixels when fitting."),
      ))
def img_resize(inputs, params, outdir):
    from PIL import Image

    try:
        value = float(params.get("value") or 50)
    except (TypeError, ValueError):
        raise ToolError("Amount must be a number")
    if value <= 0:
        raise ToolError("Amount must be greater than zero")

    made = []
    for src in inputs:
        with Image.open(src) as im:
            if params.get("mode") == "max":
                scale = min(value / max(im.size), 1.0)
            else:
                scale = value / 100.0
            size = (max(1, round(im.width * scale)), max(1, round(im.height * scale)))
            resized = im.resize(size, Image.LANCZOS)
            out = outdir / f"{src.stem}_{size[0]}x{size[1]}{src.suffix}"
            resized.save(out)
        made.append(out)
    return made


@tool(id="img-rotate", label="Rotate or flip", blurb="Quarter turns and mirroring, losslessly where possible.",
      category="Image", accepts=("image",), engines=("pillow",),
      params=(
          Param("angle", "Turn by", "select", "90",
                (("0", "Don't turn"), ("90", "90 clockwise"), ("180", "180"),
                 ("270", "90 anticlockwise"))),
          Param("flip", "Mirror", "select", "none",
                (("none", "No"), ("h", "Horizontally"), ("v", "Vertically"))),
      ))
def img_rotate(inputs, params, outdir):
    from PIL import Image

    angle = int(params.get("angle") or 0)
    flip = params.get("flip", "none")
    made = []
    for src in inputs:
        with Image.open(src) as im:
            if angle:
                im = im.rotate(-angle, expand=True)   # PIL turns anticlockwise
            if flip == "h":
                im = im.transpose(Image.FLIP_LEFT_RIGHT)
            elif flip == "v":
                im = im.transpose(Image.FLIP_TOP_BOTTOM)
            out = outdir / f"{src.stem}_turned{src.suffix}"
            im.save(out)
        made.append(out)
    return made
