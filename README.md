# ytdlp-mcp-server

A local MCP (Model Context Protocol) server that wraps [yt-dlp](https://github.com/yt-dlp/yt-dlp) to give AI assistants the ability to download videos, audio, and transcripts. No YouTube API key required.

## Prerequisites

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) on your PATH (required for audio extraction and format conversion)
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

## Quick Start

```bash
# Run with uv (auto-installs dependencies)
uv run server.py
```

Or install dependencies manually:

```bash
pip install "mcp[cli]>=1.2.0" "yt-dlp>=2024.10.0"
python server.py
```

## Tools

| Tool | Description |
|------|-------------|
| `get_transcript` | Fetch a video's captions as plain text. Prefers manual subtitles, falls back to auto-generated. |
| `download_subtitles` | Write subtitle files to disk in vtt, srt, ass, or json3 format. |
| `download_audio` | Download audio and convert to mp3, m4a, opus, wav, or flac. |
| `download_video` | Download video with optional resolution cap (default 1080p), merged to mp4, mkv, or webm. |

All download tools default to `~/Downloads` as the output directory.

## MCP Client Configuration

Add to your MCP client config (e.g. Claude Desktop `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ytdlp-local": {
      "command": "uv",
      "args": ["run", "/path/to/server.py"]
    }
  }
}
```

## Examples

Once connected via an MCP client:

- **Get a transcript:** `get_transcript(url="https://youtube.com/watch?v=...", language="en")`
- **Download audio as MP3:** `download_audio(url="https://youtube.com/watch?v=...", audio_format="mp3", quality="192")`
- **Download 720p video:** `download_video(url="https://youtube.com/watch?v=...", max_height=720)`
- **Save subtitles as SRT:** `download_subtitles(url="https://youtube.com/watch?v=...", subtitle_format="srt")`

## License

MIT
