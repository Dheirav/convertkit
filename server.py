"""convertkit: a local file converter.

Runs on 127.0.0.1 only. Files land in jobs/<id>/, get converted in place, and
the directory is swept an hour later. Nothing leaves the machine.
"""
from __future__ import annotations

import json
import re
import shutil
import time
import traceback
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

import registry
from registry import TOOLS, ToolError

BASE = Path(__file__).resolve().parent
JOBS = BASE / "jobs"
STATIC = BASE / "static"
JOB_TTL = 60 * 60          # keep results an hour
MAX_BYTES = 2 * 1024**3    # 2 GB per upload, mostly to catch mistakes

app = FastAPI(title="convertkit")
registry.load_tools()


# --- helpers ----------------------------------------------------------------
_SAFE = re.compile(r"[^A-Za-z0-9._ -]")


def safe_name(name: str) -> str:
    """Filenames are user input and end up as argv. Flatten to a basename and
    strip anything that isn't plainly a filename."""
    base = Path(name or "file").name
    base = _SAFE.sub("_", base).strip(". ") or "file"
    return base[:120]


def sweep_jobs() -> None:
    cutoff = time.time() - JOB_TTL
    if not JOBS.exists():
        return
    for entry in JOBS.iterdir():
        try:
            if entry.is_dir() and entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
        except OSError:
            pass


def job_dir(job_id: str) -> Path:
    """Resolve a job id without letting it climb out of jobs/."""
    if not re.fullmatch(r"[0-9a-f]{32}", job_id or ""):
        raise HTTPException(400, "Bad job id")
    path = (JOBS / job_id).resolve()
    if not path.is_dir() or JOBS.resolve() not in path.parents:
        raise HTTPException(404, "That job has expired")
    return path


# --- api --------------------------------------------------------------------
@app.get("/api/catalog")
def catalog():
    registry.refresh_engines()
    return {
        "tools": [t.to_json() for t in TOOLS.values()],
        "engines": registry.engine_report(),
        "groups": {g: list(exts) for g, exts in registry.GROUPS.items()},
    }


@app.post("/api/run")
async def run(tool_id: str = Form(...), params: str = Form("{}"), files: list[UploadFile] = []):
    sweep_jobs()
    tool = TOOLS.get(tool_id)
    if tool is None:
        raise HTTPException(404, "No such tool")
    if not tool.available:
        raise HTTPException(400, f"Needs {', '.join(tool.missing)}")
    if not files:
        raise HTTPException(400, "No files given")
    if len(files) > 1 and not tool.multi:
        raise HTTPException(400, f"{tool.label} takes one file at a time")

    try:
        parsed = json.loads(params or "{}")
        if not isinstance(parsed, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(400, "Bad parameters")

    job_id = uuid.uuid4().hex
    root = JOBS / job_id
    indir, outdir = root / "in", root / "out"
    outdir.mkdir(parents=True)
    indir.mkdir(parents=True)

    saved: list[Path] = []
    total = 0
    try:
        for upload in files:
            dest = indir / safe_name(upload.filename)
            if dest.exists():
                dest = indir / f"{dest.stem}_{len(saved)}{dest.suffix}"
            with dest.open("wb") as fh:
                while chunk := await upload.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise HTTPException(413, "That is over the 2 GB limit")
                    fh.write(chunk)
            saved.append(dest)

        groups = {registry.sniff_group(p) or registry.group_of(p.name) for p in saved}
        groups.discard(None)
        if "*" not in tool.accepts and not (groups & set(tool.accepts)):
            raise HTTPException(400, f"{tool.label} does not take {', '.join(sorted(groups)) or 'that'} files")

        started = time.time()
        # Converters are blocking and can run for minutes. Off the event loop
        # they go, or a single big video freezes the whole server.
        produced = await run_in_threadpool(tool.run, saved, parsed, outdir)
        produced = [p for p in produced if p.exists() and p.is_file() and p.parent == outdir]
        if not produced:
            raise ToolError("The tool produced no output")

        return {
            "job": job_id,
            "elapsed": round(time.time() - started, 1),
            "files": [
                {"name": p.name, "size": p.stat().st_size,
                 "url": f"/api/download/{job_id}/{p.name}"}
                for p in sorted(produced)
            ],
            "zip": f"/api/zip/{job_id}" if len(produced) > 1 else None,
        }
    except HTTPException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    except ToolError as exc:
        shutil.rmtree(root, ignore_errors=True)
        return JSONResponse({"error": str(exc)}, status_code=422)
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        traceback.print_exc()
        return JSONResponse({"error": "The converter crashed -- see the terminal for the traceback."},
                            status_code=500)
    finally:
        shutil.rmtree(indir, ignore_errors=True)


@app.get("/api/download/{job_id}/{name}")
def download(job_id: str, name: str):
    outdir = job_dir(job_id) / "out"
    path = (outdir / safe_name(name)).resolve()
    if not path.is_file() or outdir.resolve() != path.parent:
        raise HTTPException(404, "Gone")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@app.get("/api/zip/{job_id}")
def download_zip(job_id: str):
    root = job_dir(job_id)
    outdir = root / "out"
    bundle = root / "results.zip"
    if not bundle.exists():
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(outdir.iterdir()):
                if path.is_file():
                    zf.write(path, path.name)
    return FileResponse(bundle, filename="results.zip", media_type="application/zip")


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    sweep_jobs()
    uvicorn.run(app, host="127.0.0.1", port=8420)
