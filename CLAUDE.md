# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Single-file MCP (Model Context Protocol) server that wraps yt-dlp to provide video/audio downloading and transcript extraction tools. No YouTube API key required. Uses inline script metadata (PEP 723) for dependency declaration.

## Running the Server

```bash
# Run directly with uv (reads inline deps from server.py)
uv run server.py

# Or with pip-installed dependencies
pip install "mcp[cli]>=1.2.0" "yt-dlp>=2024.10.0"
python server.py
```

The server communicates via JSON-RPC over stdout. yt-dlp output is forced into quiet mode to avoid corrupting the MCP stream.

## Architecture

- **server.py** — entire codebase; uses `FastMCP` from the `mcp` SDK to register four tools:
  - `get_transcript` — fetches captions as plain text (prefers manual subs, falls back to auto)
  - `download_subtitles` — writes subtitle files to disk in vtt/srt/ass/json3
  - `download_audio` — downloads and converts to mp3/m4a/opus/wav/flac via ffmpeg
  - `download_video` — downloads with optional resolution cap, merges to mp4/mkv/webm

## Key Design Decisions

- All yt-dlp calls use `_quiet_opts()` to suppress console output — stdout is reserved for MCP JSON-RPC.
- Default output directory is `~/Downloads` for all download tools.
- `_strip_vtt()` deduplicates caption lines and strips VTT markup/timestamps to produce clean plain text.
- Dependencies: requires `ffmpeg` on PATH for audio extraction and format conversion.
