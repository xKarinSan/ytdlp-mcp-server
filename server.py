# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp[cli]>=1.2.0",
#     "yt-dlp>=2024.10.0",
# ]
# ///
"""Local MCP server wrapping yt-dlp. No YouTube API key required.

Exposes seven tools:
  - get_transcript: return captions as plain text
  - extract_key_frames: auto-detect visually significant moments (scene changes)
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


MAX_RESPONSE_BYTES = 900_000  # stay safely under MCP's ~1MB tool response limit


def _extract_frame_jpeg(
    video_path: str,
    ts: float,
    out_path: str,
    scale: int = 480,
    quality: int = 8,
) -> bool:
    """Extract a single frame as a scaled JPEG. Returns True if file was created."""
    subprocess.run(
        [
            "ffmpeg", "-ss", str(ts), "-i", video_path,
            "-vframes", "1",
            "-vf", f"scale=-2:{scale}",
            "-q:v", str(quality),
            "-y", out_path,
        ],
        capture_output=True,
    )
    return Path(out_path).exists()


def _download_and_extract_frames(
    url: str,
    timestamps: list[float],
    output_dir: str | None,
    *,
    video_path: str | None = None,
    info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Download a video (if not already provided) and extract frames.

    Strategy for staying within MCP tool response limits (~1MB):
    - Downloads video at 480p (sufficient for visual analysis, small frames).
    - Extracts frames as JPEG at q:v 8, scaled to 480p (~15-35KB each).
    - After encoding all frames, checks total base64 payload against the budget.
      If over budget, re-encodes at progressively lower quality/resolution.
    - If output_dir is set, also saves full-resolution PNG originals to disk.

    Returns a dict with title, video_id, duration, and a list of frame entries
    each containing timestamp_seconds, timestamp, base64_jpeg, and optionally file_path.
    """
    with tempfile.TemporaryDirectory() as tmp:
        if video_path is None:
            video_path = str(Path(tmp) / "video.mp4")
            opts = {
                **_quiet_opts(),
                "format": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
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

        # Try progressively smaller settings until frames fit within budget
        scale_quality_levels = [(480, 8), (360, 10), (240, 12)]

        frame_paths: list[Path] = []
        used_level = scale_quality_levels[0]

        for scale, quality in scale_quality_levels:
            frame_paths.clear()
            for i, ts in enumerate(timestamps):
                out_path = frames_dir / f"frame_{i:04d}.jpg"
                if _extract_frame_jpeg(video_path, ts, str(out_path), scale, quality):
                    frame_paths.append(out_path)

            # Check total base64 size (base64 expands by ~4/3)
            raw_total = sum(p.stat().st_size for p in frame_paths)
            b64_total = (raw_total * 4) // 3
            used_level = (scale, quality)
            if b64_total <= MAX_RESPONSE_BYTES:
                break

        # If output_dir specified, also save full-res originals
        save_dir = _expand_dir(output_dir) if output_dir else None
        if save_dir:
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
            "frame_resolution": f"{used_level[0]}p",
            "frames": frames_data,
        }


def _detect_scene_changes(
    video_path: str,
    threshold: float = 0.3,
    max_frames: int = 20,
    min_gap: float = 2.0,
) -> list[float]:
    """Use ffmpeg scene detection to find timestamps where visuals change significantly.

    threshold: scene change sensitivity (0.0-1.0). Lower = more sensitive.
        0.3 works well for slides/diagrams, use 0.2 for subtle changes.
    min_gap: minimum seconds between detected scenes to avoid duplicates.
    """
    result = subprocess.run(
        [
            "ffmpeg", "-i", video_path,
            "-vf", f"select='gt(scene,{threshold})',showinfo",
            "-vsync", "vfr",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    # Parse timestamps from ffmpeg showinfo output
    timestamps: list[float] = []
    for line in result.stderr.splitlines():
        match = re.search(r"pts_time:([\d.]+)", line)
        if match:
            ts = float(match.group(1))
            # Enforce minimum gap between frames
            if not timestamps or (ts - timestamps[-1]) >= min_gap:
                timestamps.append(ts)
            if len(timestamps) >= max_frames:
                break
    return timestamps


@mcp.tool()
def extract_key_frames(
    url: str,
    threshold: float = 0.3,
    max_frames: int = 20,
    min_gap: float = 2.0,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Auto-detect and capture visually significant moments from a video.

    Uses ffmpeg scene change detection to find frames where the visual content
    changes substantially — slide transitions, new diagrams, topic shifts, etc.
    Much more accurate than fixed intervals for videos with visual content.

    Returns compact base64 JPEGs (auto-scaled to fit within MCP size limits).
    If output_dir is set, also saves full-resolution PNG originals to disk.

    threshold: scene change sensitivity (0.0-1.0, default 0.3).
        Lower values detect more subtle changes. Use 0.2 for dense content.
    max_frames: cap on total frames returned (default 20).
    min_gap: minimum seconds between detected scenes (default 2.0).
    output_dir: if provided, also saves full-res frames to disk.
    """
    with tempfile.TemporaryDirectory() as tmp:
        video_path = str(Path(tmp) / "video_detect.mp4")
        opts = {
            **_quiet_opts(),
            "format": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
            "merge_output_format": "mp4",
            "outtmpl": video_path,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        timestamps = _detect_scene_changes(video_path, threshold, max_frames, min_gap)

        if not timestamps:
            # Fallback: if no scene changes detected, grab a frame at the start
            timestamps = [0.0]

        # Reuse the already-downloaded video instead of downloading again
        result = _download_and_extract_frames(
            url, timestamps, output_dir,
            video_path=video_path, info=info,
        )
        result["detection_threshold"] = threshold
        result["min_gap_seconds"] = min_gap
        return result


@mcp.tool()
def extract_frames(
    url: str,
    interval_seconds: float = 10.0,
    max_frames: int = 20,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Extract frames from a video at regular intervals for visual analysis.

    Returns compact base64 JPEGs (auto-scaled to fit within MCP size limits).
    If output_dir is set, also saves full-resolution PNG originals to disk.

    interval_seconds: time between captures (default 10s).
    max_frames: cap on total frames returned (default 20).
    output_dir: if provided, also saves full-res frames to disk.
    """
    # Download once and use the video for both duration detection and frame extraction
    with tempfile.TemporaryDirectory() as tmp:
        video_path = str(Path(tmp) / "video.mp4")
        opts = {
            **_quiet_opts(),
            "format": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
            "merge_output_format": "mp4",
            "outtmpl": video_path,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        duration = info.get("duration") or 0

        timestamps: list[float] = []
        t = 0.0
        while t < duration and len(timestamps) < max_frames:
            timestamps.append(t)
            t += interval_seconds
        if not timestamps:
            timestamps = [0.0]

        result = _download_and_extract_frames(
            url, timestamps, output_dir,
            video_path=video_path, info=info,
        )
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
    Returns compact base64 JPEGs (auto-scaled to fit within MCP size limits).
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
