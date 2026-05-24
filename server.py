# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp[cli]>=1.2.0",
#     "yt-dlp>=2024.10.0",
# ]
# ///
"""Local MCP server wrapping yt-dlp. No YouTube API key required.

Exposes six tools:
  - get_transcript: return captions as plain text
  - extract_frames: capture frames at regular intervals for visual analysis
  - snapshot: capture frames at specific user-supplied timestamps
  - download_subtitles: write subtitle file(s) to disk
  - download_audio: download + convert to mp3/m4a/etc.
  - download_video: download (optionally capped resolution) and merge to mp4

yt-dlp output is forced into quiet mode so it never writes to stdout — stdout
is reserved for the MCP JSON-RPC stream.
"""

from __future__ import annotations

import base64
import re
import subprocess
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


def _parse_timestamp(ts: str) -> float:
    """Parse a timestamp string like '1:23', '02:45', '1:02:30', or '90' into seconds."""
    parts = ts.strip().split(":")
    parts = [float(p) for p in parts]
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _format_timestamp(seconds: float) -> str:
    """Format seconds into MM:SS or HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _download_and_extract_frames(
    url: str,
    timestamps: list[float],
    output_dir: str | None,
) -> dict[str, Any]:
    """Download a video and extract frames at the given timestamps.

    Strategy for staying within MCP tool response limits:
    - Downloads video at 720p (sufficient for visual analysis, keeps frames small).
    - Extracts frames as high-quality JPEG (q:v 2 ≈ 95% quality, ~50-150KB each).
    - If output_dir is set, also saves full-resolution PNG originals to disk.

    Returns a dict with title, video_id, duration, and a list of frame entries
    each containing timestamp_seconds, timestamp, base64_jpeg, and optionally file_path.
    """
    with tempfile.TemporaryDirectory() as tmp:
        video_path = str(Path(tmp) / "video.mp4")
        # Download at 720p for base64 response (keeps payload manageable)
        opts = {
            **_quiet_opts(),
            "format": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
            "merge_output_format": "mp4",
            "outtmpl": video_path,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        title = info.get("title", "")
        video_id = info.get("id", "")
        duration = info.get("duration") or 0

        frames_dir = Path(tmp) / "frames"
        frames_dir.mkdir()

        # Extract frames as JPEG (high quality, compact size)
        frame_paths: list[Path] = []
        for i, ts in enumerate(timestamps):
            out_path = frames_dir / f"frame_{i:04d}.jpg"
            subprocess.run(
                [
                    "ffmpeg", "-ss", str(ts), "-i", video_path,
                    "-vframes", "1",
                    "-q:v", "2",
                    "-y", str(out_path),
                ],
                capture_output=True,
            )
            if out_path.exists():
                frame_paths.append(out_path)

        # If output_dir specified, also save full-res originals
        save_dir = _expand_dir(output_dir) if output_dir else None
        if save_dir:
            # Re-download at best quality for disk saves
            full_video_path = str(Path(tmp) / "video_full.mp4")
            full_opts = {
                **_quiet_opts(),
                "format": "bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
                "outtmpl": full_video_path,
            }
            with yt_dlp.YoutubeDL(full_opts) as ydl:
                ydl.extract_info(url, download=True)

            for i, ts in enumerate(timestamps):
                save_path = save_dir / f"{title} [{video_id}] frame_{ts:.1f}s.png"
                subprocess.run(
                    [
                        "ffmpeg", "-ss", str(ts), "-i", full_video_path,
                        "-vframes", "1",
                        "-y", str(save_path),
                    ],
                    capture_output=True,
                )

        frames_data: list[dict[str, Any]] = []
        for path, ts in zip(frame_paths, timestamps):
            image_bytes = path.read_bytes()
            entry: dict[str, Any] = {
                "timestamp_seconds": ts,
                "timestamp": _format_timestamp(ts),
                "base64_jpeg": base64.b64encode(image_bytes).decode("ascii"),
            }
            if save_dir:
                save_path = save_dir / f"{title} [{video_id}] frame_{ts:.1f}s.png"
                if save_path.exists():
                    entry["file_path"] = str(save_path)
            frames_data.append(entry)

        return {
            "title": title,
            "video_id": video_id,
            "duration_seconds": duration,
            "frame_count": len(frames_data),
            "frames": frames_data,
        }


@mcp.tool()
def extract_frames(
    url: str,
    interval_seconds: float = 10.0,
    max_frames: int = 20,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Extract frames from a video at regular intervals for visual analysis.

    Returns compact base64 JPEGs (720p) in the response for the LLM to analyze.
    If output_dir is set, also saves full-resolution PNG originals to disk.

    interval_seconds: time between captures (default 10s).
    max_frames: cap on total frames returned (default 20).
    output_dir: if provided, also saves full-res frames to disk.
    """
    # Fetch duration first to compute timestamps
    with yt_dlp.YoutubeDL({**_quiet_opts(), "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    duration = info.get("duration") or 0

    timestamps: list[float] = []
    t = 0.0
    while t < duration and len(timestamps) < max_frames:
        timestamps.append(t)
        t += interval_seconds
    if not timestamps:
        timestamps = [0.0]

    result = _download_and_extract_frames(url, timestamps, output_dir)
    result["interval_seconds"] = interval_seconds
    return result


@mcp.tool()
def snapshot(
    url: str,
    timestamps: list[str],
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Capture frames at specific timestamps from a video.

    Use this when the user requests snapshots/screenshots at particular moments.
    Returns compact base64 JPEGs (720p) in the response for the LLM to analyze.
    If output_dir is set, also saves full-resolution PNG originals to disk.

    timestamps: list of timestamp strings, e.g. ["0:30", "2:45", "1:02:30"].
        Supports formats: "SS", "MM:SS", "HH:MM:SS".
    output_dir: if provided, also saves full-res frames to disk.
    """
    parsed = [_parse_timestamp(ts) for ts in timestamps]
    return _download_and_extract_frames(url, parsed, output_dir)


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
