# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp[cli]>=1.2.0",
#     "yt-dlp>=2024.10.0",
# ]
# ///
"""Local MCP server wrapping yt-dlp. No YouTube API key required.

Exposes four tools:
  - get_transcript: return captions as plain text
  - download_subtitles: write subtitle file(s) to disk
  - download_audio: download + convert to mp3/m4a/etc.
  - download_video: download (optionally capped resolution) and merge to mp4

yt-dlp output is forced into quiet mode so it never writes to stdout — stdout
is reserved for the MCP JSON-RPC stream.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

import yt_dlp
from mcp.server.fastmcp import FastMCP

DEFAULT_OUTPUT_DIR = Path.home() / "Downloads"

mcp = FastMCP("ytdlp-local")


def _expand_dir(output_dir: str | None) -> Path:
    path = Path(output_dir).expanduser() if output_dir else DEFAULT_OUTPUT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _final_path(info: dict[str, Any]) -> Path | None:
    downloads = info.get("requested_downloads") or []
    if downloads and downloads[0].get("filepath"):
        return Path(downloads[0]["filepath"])
    fn = info.get("_filename") or info.get("filename")
    return Path(fn) if fn else None


def _quiet_opts() -> dict[str, Any]:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "consoletitle": False,
    }


def _strip_vtt(vtt_text: str) -> str:
    """Convert WebVTT to plain text, deduping repeated cue lines."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in vtt_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        if "-->" in line:
            continue
        if re.fullmatch(r"\d+", line):
            continue
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
    return "\n".join(out)


@mcp.tool()
def get_transcript(url: str, language: str = "en") -> dict[str, Any]:
    """Fetch a video's captions as plain text.

    Prefers manual subtitles, falls back to auto-generated. Returns a dict
    with `text`, `language`, `source` ("manual" | "auto"), `title`, `video_id`.
    """
    with tempfile.TemporaryDirectory() as tmp:
        opts = {
            **_quiet_opts(),
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": [language],
            "subtitlesformat": "vtt",
            "outtmpl": str(Path(tmp) / "%(id)s"),
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        files = sorted(Path(tmp).glob(f"*.{language}*.vtt"))
        if not files:
            return {
                "error": f"No subtitles available for language={language!r}",
                "available_manual": list((info.get("subtitles") or {}).keys()),
                "available_auto": list((info.get("automatic_captions") or {}).keys()),
            }

        has_manual = bool((info.get("subtitles") or {}).get(language))
        source = "manual" if has_manual else "auto"

        return {
            "text": _strip_vtt(files[0].read_text(encoding="utf-8")),
            "language": language,
            "source": source,
            "title": info.get("title"),
            "video_id": info.get("id"),
        }


@mcp.tool()
def download_subtitles(
    url: str,
    language: str = "en",
    output_dir: str | None = None,
    subtitle_format: str = "vtt",
    include_auto: bool = True,
) -> dict[str, Any]:
    """Write subtitle file(s) to disk (default: ~/Downloads).

    subtitle_format: vtt | srt | ass | json3 (yt-dlp converts via ffmpeg if needed).
    Returns dict with `file_paths`, `title`, `video_id`.
    """
    out = _expand_dir(output_dir)
    opts = {
        **_quiet_opts(),
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": include_auto,
        "subtitleslangs": [language],
        "subtitlesformat": subtitle_format,
        "outtmpl": str(out / "%(title)s [%(id)s]"),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    files = sorted(out.glob(f"*[{info.get('id', '')}]*.{language}*.{subtitle_format}"))
    return {
        "file_paths": [str(p) for p in files],
        "title": info.get("title"),
        "video_id": info.get("id"),
    }


@mcp.tool()
def download_audio(
    url: str,
    output_dir: str | None = None,
    audio_format: str = "mp3",
    quality: str = "192",
) -> dict[str, Any]:
    """Download audio and convert via ffmpeg.

    audio_format: mp3 | m4a | opus | wav | flac.
    quality: bitrate (e.g. "192") for lossy codecs; ignored for lossless.
    Defaults output to ~/Downloads.
    """
    out = _expand_dir(output_dir)
    opts = {
        **_quiet_opts(),
        "format": "bestaudio/best",
        "outtmpl": str(out / "%(title)s [%(id)s].%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
                "preferredquality": quality,
            }
        ],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    path = _final_path(info)
    return {
        "file_path": str(path) if path else None,
        "title": info.get("title"),
        "duration_seconds": info.get("duration"),
        "video_id": info.get("id"),
    }


@mcp.tool()
def download_video(
    url: str,
    output_dir: str | None = None,
    max_height: int | None = 1080,
    container: str = "mp4",
) -> dict[str, Any]:
    """Download a video, optionally capping resolution, and merge to `container`.

    max_height: cap on vertical resolution (e.g. 720, 1080); None for best.
    container: mp4 | mkv | webm.
    Defaults output to ~/Downloads.
    """
    out = _expand_dir(output_dir)
    if max_height:
        fmt = (
            f"bestvideo[height<={max_height}]+bestaudio/"
            f"best[height<={max_height}]/best"
        )
    else:
        fmt = "bestvideo+bestaudio/best"

    opts = {
        **_quiet_opts(),
        "format": fmt,
        "merge_output_format": container,
        "outtmpl": str(out / "%(title)s [%(id)s].%(ext)s"),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    path = _final_path(info)
    width, height = info.get("width"), info.get("height")
    return {
        "file_path": str(path) if path else None,
        "title": info.get("title"),
        "duration_seconds": info.get("duration"),
        "resolution": f"{width}x{height}" if width and height else None,
        "video_id": info.get("id"),
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
