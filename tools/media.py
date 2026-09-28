"""Audio and video -- one ffmpeg, several sensible presets."""
from __future__ import annotations

from registry import Param, ToolError, run_cmd, tool

VIDEO_TARGETS = (("mp4", "MP4 (H.264)"), ("webm", "WebM (VP9)"), ("mkv", "MKV"), ("gif", "Animated GIF"))
AUDIO_TARGETS = (("mp3", "MP3"), ("m4a", "AAC (.m4a)"), ("wav", "WAV"), ("flac", "FLAC"), ("ogg", "Ogg Vorbis"))
QUALITY = (("high", "High quality, bigger"), ("balanced", "Balanced"), ("small", "Small file"))
_CRF = {"high": "20", "balanced": "26", "small": "32"}
_ABR = {"high": "256k", "balanced": "192k", "small": "128k"}


@tool(id="video-convert", label="Convert video", blurb="Re-encode to MP4, WebM, MKV or a GIF.",
      category="Media", accepts=("video",), engines=("ffmpeg",),
      params=(
          Param("target", "To", "select", "mp4", VIDEO_TARGETS),
          Param("quality", "Quality", "select", "balanced", QUALITY),
          Param("width", "Scale width to", "number", 0,
                help="Pixels. 0 keeps the original size. Height follows automatically."),
      ))
def video_convert(inputs, params, outdir):
    src = inputs[0]
    target = params.get("target", "mp4")
    quality = params.get("quality", "balanced")
    try:
        width = int(params.get("width") or 0)
    except (TypeError, ValueError):
        width = 0

    out = outdir / f"{src.stem}_converted.{target}"
    args = ["ffmpeg", "-y", "-i", str(src)]
    filters = []
    if width > 0:
        filters.append(f"scale={width}:-2")

    if target == "gif":
        filters.insert(0, "fps=12")
        args += ["-vf", ",".join(filters) if filters else "fps=12", "-loop", "0"]
    elif target == "webm":
        if filters:
            args += ["-vf", ",".join(filters)]
        args += ["-c:v", "libvpx-vp9", "-crf", _CRF[quality], "-b:v", "0", "-c:a", "libopus"]
    else:
        if filters:
            args += ["-vf", ",".join(filters)]
        args += ["-c:v", "libx264", "-crf", _CRF[quality], "-preset", "medium",
                 "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"]
    args.append(str(out))
    run_cmd(args, timeout=3600)
    return [out]


@tool(id="video-to-audio", label="Extract audio", blurb="Pull the soundtrack out of a video.",
      category="Media", accepts=("video",), engines=("ffmpeg",),
      params=(
          Param("target", "To", "select", "mp3", AUDIO_TARGETS),
          Param("quality", "Bitrate", "select", "balanced", QUALITY),
      ))
def video_to_audio(inputs, params, outdir):
    return _to_audio(inputs[0], params, outdir)


@tool(id="audio-convert", label="Convert audio", blurb="Between MP3, AAC, WAV, FLAC and Ogg.",
      category="Media", accepts=("audio",), engines=("ffmpeg",),
      params=(
          Param("target", "To", "select", "mp3", AUDIO_TARGETS),
          Param("quality", "Bitrate", "select", "balanced", QUALITY),
      ))
def audio_convert(inputs, params, outdir):
    return _to_audio(inputs[0], params, outdir)


def _to_audio(src, params, outdir):
    target = params.get("target", "mp3")
    if target not in {t[0] for t in AUDIO_TARGETS}:
        raise ToolError("Unsupported audio format")
    bitrate = _ABR.get(params.get("quality", "balanced"), "192k")
    out = outdir / f"{src.stem}.{target}"
    args = ["ffmpeg", "-y", "-i", str(src), "-vn"]
    if target == "wav":
        args += ["-c:a", "pcm_s16le"]
    elif target == "flac":
        args += ["-c:a", "flac"]
    elif target == "m4a":
        args += ["-c:a", "aac", "-b:a", bitrate]
    elif target == "ogg":
        args += ["-c:a", "libvorbis", "-b:a", bitrate]
    else:
        args += ["-c:a", "libmp3lame", "-b:a", bitrate]
    args.append(str(out))
    run_cmd(args, timeout=1800)
    return [out]
