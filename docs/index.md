# ytdlp-mcp-server Documentation

A local MCP (Model Context Protocol) server that wraps [yt-dlp](https://github.com/yt-dlp/yt-dlp) to give AI assistants the ability to download videos, audio, transcripts, and extract visual frames from online videos. No YouTube API key required.

## What is this?

This server exposes seven tools over the MCP protocol, allowing any MCP-compatible AI client (such as Claude Desktop or Claude Code) to:

- Fetch video transcripts as clean plain text
- Download audio in multiple formats (mp3, m4a, opus, wav, flac)
- Download video with optional resolution caps
- Save subtitle files in various formats
- Extract frames at regular intervals for visual analysis
- Auto-detect visually significant moments (scene changes) and capture them
- Capture frames at specific user-supplied timestamps

## Documentation

| Page | Description |
|------|-------------|
| [Getting Started](getting-started.md) | Prerequisites, installation, and running the server |
| [Tools Reference](tools-reference.md) | Detailed documentation for all seven MCP tools |
| [Configuration](configuration.md) | MCP client configuration for Claude Desktop, Claude Code, and other clients |
| [Architecture](architecture.md) | Technical design, internal helpers, and design decisions |
| [Diagrams](diagram.md) | Mermaid diagrams: architecture, request lifecycle, frame extraction, transcript flow |

## Quick Start

```bash
# Run with uv (auto-installs dependencies via PEP 723 inline metadata)
uv run server.py
```

See the [Getting Started](getting-started.md) guide for full setup instructions.
