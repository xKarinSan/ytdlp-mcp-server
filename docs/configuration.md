# Configuration

This server uses the MCP (Model Context Protocol) and is designed to be launched by an MCP client. Below are configuration examples for common clients.

## Claude Desktop

Add the following to your Claude Desktop configuration file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "ytdlp-local": {
      "command": "uv",
      "args": ["run", "/absolute/path/to/server.py"]
    }
  }
}
```

Replace `/absolute/path/to/server.py` with the actual path to your `server.py` file.

## Claude Code

Add the server to your Claude Code MCP configuration:

```bash
claude mcp add ytdlp-local -- uv run /absolute/path/to/server.py
```

Or add it to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "ytdlp-local": {
      "command": "uv",
      "args": ["run", "/absolute/path/to/server.py"]
    }
  }
}
```

## Generic MCP Client

Any MCP client that supports the stdio transport can launch this server. The command is:

```bash
uv run /path/to/server.py
```

The server communicates via JSON-RPC over stdin/stdout. The server name registered with FastMCP is `"ytdlp-local"`.

## Environment Requirements

The server process requires:

1. **`ffmpeg` on `PATH`** — used for audio extraction, format conversion, and frame capture
2. **Network access** — to download videos from supported sites
3. **Write access to `~/Downloads`** (or whatever `output_dir` you specify per tool call)

## Supported Sites

This server supports any site that yt-dlp supports. See the [yt-dlp supported sites list](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md) for the full catalog, which includes YouTube, Vimeo, Twitter/X, Reddit, and many more.
