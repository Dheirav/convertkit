"""Tool registry: what we can convert, into what, using which engine.

Everything the UI knows comes from here. A tool declares the file groups it
accepts and the engines it needs; the probe below decides at runtime whether
it is actually usable on this machine, so a missing LibreOffice greys out the
office tools instead of exploding halfway through a job.
"""
from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# --- file type groups -------------------------------------------------------
# Extension -> group. Detection is extension-first because the browser gives us
# a filename and users trust it; sniff_group() second-guesses it only for the
# handful of signatures that are cheap and unambiguous.
GROUPS: dict[str, tuple[str, ...]] = {
    "pdf": ("pdf",),
    "image": ("png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp", "gif", "heic", "avif", "ppm"),
    "office": ("doc", "docx", "odt", "rtf", "xls", "xlsx", "ods", "ppt", "pptx", "odp", "csv"),
    "markup": ("md", "markdown", "html", "htm", "rst", "tex", "epub", "txt"),
    "video": ("mp4", "mkv", "mov", "avi", "webm", "wmv", "flv", "m4v", "mpg", "mpeg"),
    "audio": ("mp3", "wav", "flac", "aac", "ogg", "m4a", "opus", "wma"),
}
EXT_GROUP: dict[str, str] = {e: g for g, exts in GROUPS.items() for e in exts}

_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "image"),
    (b"\xff\xd8\xff", "image"),
    (b"GIF8", "image"),
    (b"BM", "image"),
)


def group_of(name: str) -> str | None:
    return EXT_GROUP.get(Path(name).suffix.lower().lstrip("."))


def sniff_group(path: Path) -> str | None:
    """Trust the bytes over the extension when we recognise the signature."""
    try:
        head = path.open("rb").read(16)
    except OSError:
        return None
    for sig, grp in _MAGIC:
        if head.startswith(sig):
            return grp
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image"
    return None


# --- engines ----------------------------------------------------------------
# ("cmd", name) -> on PATH.  ("mod", name) -> importable in this interpreter.
# A tuple of alternatives means any one of them satisfies the engine.
ENGINE_CHECKS: dict[str, tuple[tuple[str, str], ...]] = {
    "qpdf": (("cmd", "qpdf"),),
    "ghostscript": (("cmd", "gs"),),
    "poppler": (("cmd", "pdftoppm"),),
    "mutool": (("cmd", "mutool"),),
    "ffmpeg": (("cmd", "ffmpeg"),),
    "tesseract": (("cmd", "tesseract"),),
    "libreoffice": (("cmd", "soffice"), ("cmd", "libreoffice")),
    "pandoc": (("cmd", "pandoc"),),
    "imagemagick": (("cmd", "magick"), ("cmd", "convert")),
    "pillow": (("mod", "PIL"),),
    "pypdf": (("mod", "pypdf"),),
    "pikepdf": (("mod", "pikepdf"),),
    "img2pdf": (("mod", "img2pdf"),),
    "ocrmypdf": (("mod", "ocrmypdf"),),
    "pdf2docx": (("mod", "pdf2docx"),),
    "reportlab": (("mod", "reportlab"),),
}

# Shown to the user when a tool is unavailable, so the fix is obvious.
ENGINE_HINT: dict[str, str] = {
    "libreoffice": "sudo apt install libreoffice",
    "pandoc": "sudo apt install pandoc",
    "imagemagick": "sudo apt install imagemagick",
    "tesseract": "sudo apt install tesseract-ocr",
    "ffmpeg": "sudo apt install ffmpeg",
    "qpdf": "sudo apt install qpdf",
    "ghostscript": "sudo apt install ghostscript",
    "poppler": "sudo apt install poppler-utils",
    "mutool": "sudo apt install mupdf-tools",
    "ocrmypdf": ".venv/bin/pip install ocrmypdf",
    "pdf2docx": ".venv/bin/pip install pdf2docx",
    "img2pdf": ".venv/bin/pip install img2pdf",
    "reportlab": ".venv/bin/pip install reportlab",
}

_engine_cache: dict[str, bool] = {}


def have_engine(name: str) -> bool:
    if name not in _engine_cache:
        checks = ENGINE_CHECKS.get(name, ())
        ok = False
        for kind, target in checks:
            if kind == "cmd" and shutil.which(target):
                ok = True
            elif kind == "mod":
                try:
                    importlib.import_module(target)
                    ok = True
                except Exception:
                    pass
            if ok:
                break
        _engine_cache[name] = ok
    return _engine_cache[name]


def refresh_engines() -> None:
    """Re-probe. Installing an engine should only cost a page reload."""
    _engine_cache.clear()


def engine_report() -> dict[str, dict[str, Any]]:
    return {
        name: {"available": have_engine(name), "hint": ENGINE_HINT.get(name, "")}
        for name in sorted(ENGINE_CHECKS)
    }


def which_office() -> str:
    return shutil.which("soffice") or shutil.which("libreoffice") or "soffice"


def which_magick() -> list[str]:
    return ["magick"] if shutil.which("magick") else ["convert"]


class ToolError(Exception):
    """A conversion failed in a way worth showing the user verbatim."""


def run_cmd(args: list[str], timeout: int = 900, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run an engine. Always a list, never a shell -- filenames are user input."""
    try:
        proc = subprocess.run(
            [str(a) for a in args],
            capture_output=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
        )
    except FileNotFoundError:
        raise ToolError(f"{args[0]} is not installed")
    except subprocess.TimeoutExpired:
        raise ToolError(f"{args[0]} timed out after {timeout}s")
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout).decode("utf-8", "replace").strip()
        tail = "\n".join(err.splitlines()[-6:]) or f"exit {proc.returncode}"
        raise ToolError(tail)
    return proc


def py_module(module: str, *args: str) -> list[str]:
    """Invoke a venv module by interpreter path, not by PATH lookup."""
    return [sys.executable, "-m", module, *args]


# --- tool definitions -------------------------------------------------------
@dataclass
class Param:
    name: str
    label: str
    kind: str = "text"                      # text | number | select | bool | password
    default: Any = None
    options: tuple[tuple[str, str], ...] = ()   # (value, label)
    placeholder: str = ""
    help: str = ""
    required: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name, "label": self.label, "kind": self.kind,
            "default": self.default, "options": [list(o) for o in self.options],
            "placeholder": self.placeholder, "help": self.help, "required": self.required,
        }


@dataclass
class Tool:
    id: str
    label: str
    blurb: str
    category: str
    accepts: tuple[str, ...]                # group names, or ("*",)
    run: Callable[[list[Path], dict, Path], list[Path]]
    multi: bool = False                     # consumes several inputs at once
    engines: tuple[str, ...] = ()
    params: tuple[Param, ...] = ()

    @property
    def available(self) -> bool:
        return all(have_engine(e) for e in self.engines)

    @property
    def missing(self) -> list[str]:
        return [e for e in self.engines if not have_engine(e)]

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id, "label": self.label, "blurb": self.blurb,
            "category": self.category, "accepts": list(self.accepts),
            "multi": self.multi, "available": self.available,
            "missing": [{"engine": e, "hint": ENGINE_HINT.get(e, "")} for e in self.missing],
            "params": [p.to_json() for p in self.params],
        }


TOOLS: dict[str, Tool] = {}


def tool(**kwargs):
    """Register a conversion. The decorated function is its run()."""
    def deco(fn):
        t = Tool(run=fn, **kwargs)
        if t.id in TOOLS:
            raise RuntimeError(f"duplicate tool id {t.id}")
        TOOLS[t.id] = t
        return fn
    return deco


def load_tools() -> None:
    for mod in ("pdf", "images", "office", "media"):
        importlib.import_module(f"tools.{mod}")


def tools_for(groups: set[str], count: int) -> list[Tool]:
    """Tools that fit what was dropped: right type, and right arity."""
    out = []
    for t in TOOLS.values():
        if not (set(t.accepts) & groups or "*" in t.accepts):
            continue
        if count > 1 and not t.multi:
            continue
        out.append(t)
    return sorted(out, key=lambda t: (t.category, t.label))
