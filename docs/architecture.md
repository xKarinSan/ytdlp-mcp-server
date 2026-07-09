# Architecture

## Overview

The entire server is a single Python file (`server.py`) using [FastMCP](https://github.com/modelcontextprotocol/python-sdk) to register tools and handle the MCP JSON-RPC protocol over stdio.

Dependencies are declared via [PEP 723](https://peps.python.org/pep-0723/) inline script metadata at the top of `server.py`, so `uv run server.py` can resolve and install them automatically without a `pyproject.toml` or `requirements.txt`.

```
server.py
├── Inline dependency metadata (PEP 723)
├── Internal helpers
│   ├── _expand_dir()         — resolve and create output directory
│   ├── _final_path()         — extract final file path from yt-dlp info dict
│   ├── _quiet_opts()         — suppress all yt-dlp console output
│   ├── _strip_vtt()          — convert WebVTT to clean plain text
│   ├── _parse_timestamp()    — parse "MM:SS" / "HH:MM:SS" / "SS" to float
│   ├── _format_timestamp()   — format float seconds to "MM:SS" or "HH:MM:SS"
│   ├── _download_and_extract_frames() — shared frame extraction pipeline
│   └── _detect_scene_changes()        — ffmpeg scene detection
├── MCP Tools (7 total)
│   ├── get_transcript
│   ├── extract_key_frames
│   ├── extract_frames
│   ├── snapshot
│   ├── download_subtitles
│   ├── download_audio
│   └── download_video
└── main() — entry point, calls mcp.run()
```

## Key Design Decisions

### Quiet Mode

All yt-dlp calls include `_quiet_opts()` which sets `quiet`, `no_warnings`, `noprogress`, and `consoletitle=False`. This is critical because stdout is the MCP JSON-RPC transport — any stray yt-dlp output would corrupt the protocol stream.

### Frame Extraction Strategy

The frame tools (`extract_key_frames`, `extract_frames`, `snapshot`) share a common pipeline via `_download_and_extract_frames()`:

1. **Download at 720p** — sufficient for LLM visual analysis, keeps base64 payloads small
2. **Extract frames as JPEG** (quality level 2, ~95%) — compact size (~50-150KB per frame)
3. **Return base64-encoded JPEGs** in the response for the LLM to analyze directly
4. **Optionally save full-resolution PNGs** to disk if `output_dir` is provided (downloads the video again at full quality)

This dual-resolution approach balances MCP response size limits with preserving full quality when files are saved to disk.

### Scene Detection

`extract_key_frames` uses ffmpeg's `select='gt(scene,THRESHOLD)'` filter to detect visual discontinuities. This is effective for:
- Slide transitions in presentations
- New diagrams or visual aids
- Camera cuts and scene changes

A `min_gap` parameter prevents clustering of detected frames too closely together.

### VTT Processing

`_strip_vtt()` processes WebVTT subtitle text by:
1. Removing VTT headers (`WEBVTT`, `Kind:`, `Language:`, `NOTE`)
2. Removing timestamp lines (containing `-->`)
3. Removing numeric cue identifiers
4. Stripping HTML-like tags (e.g., `<c>`, `</c>`)
5. Deduplicating repeated caption lines (common in auto-generated subtitles)

This produces clean, readable plain text from raw caption data.

### Output File Naming

Download tools use yt-dlp's template system: `%(title)s [%(id)s].%(ext)s`. This produces filenames like:

```
Rick Astley - Never Gonna Give You Up [dQw4w9WgXcQ].mp3
```

The video ID in brackets ensures uniqueness when videos have similar titles.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `mcp[cli]>=1.2.0` | MCP SDK with CLI transport support |
| `yt-dlp>=2024.10.0` | Video/audio download engine |
| `ffmpeg` (system) | Audio extraction, format conversion, frame capture |

## Data Flow

```
MCP Client (e.g., Claude Desktop)
    │
    │  JSON-RPC over stdin/stdout
    │
    ▼
server.py (FastMCP)
    │
    ├──▶ yt-dlp Python API (download, metadata, subtitles)
    │
    └──▶ ffmpeg subprocess (audio conversion, frame extraction, scene detection)
```
