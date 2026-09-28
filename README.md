# convertkit

A local iLovePDF. Drop files in a browser page, pick what to do, get the result
back. Everything runs on this machine — nothing is uploaded anywhere.

## Setup

The Python side goes in a venv, and the heavy lifting is done by ordinary
command-line programs, so those come from the system package manager.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
sudo apt install qpdf ghostscript poppler-utils mupdf-tools ffmpeg \
    tesseract-ocr libreoffice pandoc imagemagick
```

None of the system programs is required to start it. A tool whose engine is
missing shows up greyed out with its install command, so you can install only
what you need.

## Running it

```bash
./run.sh                 # http://127.0.0.1:8420
PORT=9000 ./run.sh       # somewhere else
./run.sh --reload        # auto-restart while editing
```

Open <http://127.0.0.1:8420> in a browser. WSL forwards localhost, so the
Windows browser reaches it without any extra setup.

## What it does

25 tools, grouped by what you drop in.

| Category | Tools |
|---|---|
| PDF | merge, split, rotate, compress, protect, unlock, reorder pages, to image, extract text, OCR, to Word, watermark, page numbers, repair, PDF/A |
| Image | images to PDF, convert format, resize, rotate/flip |
| Documents | office to PDF, convert document, convert text format |
| Media | convert video, extract audio, convert audio |

Drop several files at once and only the batch-capable tools (merge, images to
PDF, the per-file image tools) are offered. Multi-file results come back with a
"download all as .zip".

## Engines

Each tool declares the engines it needs, and `registry.py` probes for them at
startup. A missing engine greys that tool out with the install command instead
of failing mid-job — expand *Engines on this machine* at the bottom of the page
to see the current state.

All present: qpdf, ghostscript, poppler, mutool, ffmpeg, tesseract, libreoffice,
pandoc, imagemagick, and the Python side (pypdf, pikepdf, img2pdf, Pillow,
reportlab, ocrmypdf, pdf2docx). All 25 tools are live.

The probe re-runs on every `/api/catalog` request, so installing an engine takes
effect on a page reload — no restart.

## Adding a tool

One decorated function in `tools/`. The UI builds itself from the declaration —
there is no frontend change to make.

```python
@tool(id="pdf-thing", label="Do a thing", blurb="Shown on the button.",
      category="PDF", accepts=("pdf",), engines=("qpdf",),
      params=(Param("level", "How much", "select", "mid",
                    (("low", "A little"), ("mid", "Some"))),))
def thing(inputs, params, outdir):
    out = outdir / "result.pdf"
    run_cmd(["qpdf", inputs[0], "--whatever", out])
    return [out]          # every returned path must live in outdir
```

`accepts` names groups from `GROUPS` in `registry.py`. Set `multi=True` if the
tool consumes several inputs at once. Raise `ToolError("...")` for anything the
user should see — it comes back as a clean message, not a 500.

## Layout

```
server.py      FastAPI: /api/catalog, /api/run, /api/download, /api/zip
registry.py    type groups, engine probing, Tool/Param types, run_cmd
tools/         pdf.py  images.py  office.py  media.py
static/        index.html  style.css  app.js   (no build step)
jobs/          per-job scratch, swept after an hour
```

## Notes worth keeping

- **OCR on sideways scans.** Tesseract's orientation detection needs clean text
  and scores far below its confidence floor on photographed or colour-heavy
  pages — it scored 0.08 on a scanned grade sheet and refused to rotate, so the
  OCR came out as mirrored gibberish. That is why the OCR tool has a manual
  *Page orientation* control. If the text looks like nonsense, set the turn by
  hand rather than trusting "detect automatically".
- **PDF to Word is best-effort.** `pdf2docx` reconstructs layout from positioned
  glyphs. Simple single-column documents convert well; dense tables do not. This
  is the one place a paid service genuinely beats the local stack.
- **Filenames reach argv.** `safe_name()` in `server.py` flattens every upload to
  a bare basename and strips anything but `[A-Za-z0-9._ -]`. Every engine call
  goes through `run_cmd()` as an argument list — never a shell string. Keep it
  that way when adding tools.
- **Converters must not block the event loop.** `/api/run` is `async def`, so a
  blocking `tool.run()` called directly would freeze the whole server for the
  length of the job — four parallel LibreOffice conversions took 15s instead of
  5s, and the page would not load at all during a long video encode. It goes
  through `run_in_threadpool`. Keep it that way.
- Bound to `127.0.0.1` deliberately. Don't move it to `0.0.0.0` without adding
  auth, since it will happily convert anything anyone sends it.
