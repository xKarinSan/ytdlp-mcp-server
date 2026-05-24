# Changelog

All notable changes to this project are documented in this file.

## [2026-05-24 18:07:03 +0800] — fix(snapshot): retain original resolution and quality for captured frames

- Fixed snapshot/frame extraction to preserve original video resolution instead of downscaling.
- Ensures captured frames retain full quality.

## [2026-05-24 17:39:14 +0800] — feat: add extract_frames and snapshot tools for visual content ingestion

- Added `extract_frames` tool for extracting multiple frames from a video at intervals.
- Added `snapshot` tool for capturing a single frame at a specified timestamp.
- Enables visual content ingestion workflows via MCP.

## [2026-05-22 05:21:49 +0800] — Initial commit: yt-dlp MCP server

- Initial release of the yt-dlp MCP server.
- Tools: `get_transcript`, `download_subtitles`, `download_audio`, `download_video`.
- Single-file architecture using FastMCP with PEP 723 inline script metadata.
- Quiet mode for all yt-dlp calls to preserve MCP JSON-RPC stdout stream.
