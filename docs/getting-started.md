# Getting Started

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | Required |
| [ffmpeg](https://ffmpeg.org/) | Any recent | Must be on your `PATH`. Required for audio extraction, format conversion, and frame capture. |
| [uv](https://github.com/astral-sh/uv) | Any recent | Recommended. Reads inline dependencies from `server.py` automatically. |

### Installing ffmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu / Debian:**
```bash
sudo apt install ffmpeg
```

**Windows:**
```bash
winget install ffmpeg
```

## Installation

### Option 1: Using uv (recommended)

No separate install step is needed. The server uses [PEP 723](https://peps.python.org/pep-0723/) inline script metadata to declare its dependencies. `uv` reads these automatically:

```bash
uv run server.py
```

This installs `mcp[cli]>=1.2.0` and `yt-dlp>=2024.10.0` into an isolated environment and runs the server.

### Option 2: Using pip

```bash
pip install "mcp[cli]>=1.2.0" "yt-dlp>=2024.10.0"
python server.py
```

## Running the Server

The server communicates via JSON-RPC over stdin/stdout. It is not meant to be used directly from the terminal — instead, it is launched by an MCP client (see [Configuration](configuration.md)).

```bash
# Direct launch (for testing)
uv run server.py
```

All yt-dlp output is suppressed (quiet mode) so that only MCP JSON-RPC messages appear on stdout.

## Default Output Directory

All download tools (`download_audio`, `download_video`, `download_subtitles`) save files to `~/Downloads` by default. You can override this per-call with the `output_dir` parameter.

## Verifying the Setup

1. Ensure `ffmpeg` is available:
   ```bash
   ffmpeg -version
   ```

2. Ensure `yt-dlp` can be imported:
   ```bash
   uv run python -c "import yt_dlp; print(yt_dlp.version.__version__)"
   ```

3. Ensure the MCP SDK is available:
   ```bash
   uv run python -c "from mcp.server.fastmcp import FastMCP; print('OK')"
   ```

Once all three checks pass, configure your MCP client to launch the server (see [Configuration](configuration.md)).
