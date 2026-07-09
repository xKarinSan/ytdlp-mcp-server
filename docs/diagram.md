# System Diagram

## How the MCP Server Works

This diagram shows the end-to-end flow: how a user's request travels from the AI agent down through the MCP server to fetch video content and return results.

```mermaid
flowchart TB
    User(["User"])

    User -->|"natural language request\n(e.g. 'get me the transcript of this video')"| Agent

    subgraph Agent["AI Agent (LLM)"]
        direction TB
        Claude["Claude\n(Desktop / Code / API)"]
        Claude -->|"interprets user intent\nselects appropriate tool\nconstructs parameters"| MCPClient["MCP Client Layer"]
    end

    MCPClient -->|"JSON-RPC tool call over stdin/stdout\ne.g. get_transcript(url=..., language='en')"| MCPServer

    subgraph MCPServer["ytdlp-mcp-server"]
        direction TB
        FastMCP["FastMCP Runtime\n(JSON-RPC handler)"]
        FastMCP --> Router{{"Route to Tool"}}

        Router --> T1["get_transcript\nfetch captions as text"]
        Router --> T2["extract_key_frames\nauto-detect scene changes"]
        Router --> T3["extract_frames\ncapture at intervals"]
        Router --> T4["snapshot\ncapture at timestamps"]
        Router --> T5["download_subtitles\nsave .vtt/.srt to disk"]
        Router --> T6["download_audio\nconvert to mp3/flac/etc"]
        Router --> T7["download_video\ndownload with resolution cap"]
    end

    subgraph Backend["Backend Processing"]
        direction TB
        YTDLP["yt-dlp\n(Python library)"]
        FFMPEG["ffmpeg\n(subprocess)"]
    end

    T1 & T2 & T3 & T4 & T5 & T6 & T7 --> YTDLP
    T2 & T3 & T4 & T6 --> FFMPEG

    YTDLP -->|"downloads from"| Internet

    subgraph Internet["Video Platforms"]
        direction LR
        YT["YouTube"]
        VM["Vimeo"]
        TW["Twitter/X"]
        More["1000+ sites"]
    end

    subgraph Results["Results"]
        direction LR
        Text["Plain text\n(transcripts)"]
        Frames["Base64 JPEGs\n(frames for LLM)"]
        Files["Files on disk\n(~/Downloads)"]
    end

    T1 -->|"cleaned text"| Text
    T2 & T3 & T4 -->|"720p JPEG frames"| Frames
    T5 & T6 & T7 -->|"saved files"| Files
    T2 & T3 & T4 -->|"optional full-res PNG"| Files

    Text & Frames -->|"returned in JSON-RPC response"| MCPClient
    Files -->|"file path returned in response"| MCPClient

    MCPClient -->|"LLM reads response data\n(can see images, read text)"| Claude
    Claude -->|"summarizes, analyzes,\nor confirms to user"| User

    style User fill:#f9f,stroke:#333,stroke-width:2px
    style Claude fill:#7c6df0,stroke:#333,stroke-width:2px,color:#fff
    style FastMCP fill:#2d8cf0,stroke:#333,stroke-width:2px,color:#fff
    style YTDLP fill:#ff6b6b,stroke:#333,stroke-width:2px,color:#fff
    style FFMPEG fill:#51cf66,stroke:#333,stroke-width:2px,color:#fff
```

## Request Lifecycle

```mermaid
sequenceDiagram
    participant User
    participant Client as MCP Client
    participant Server as server.py
    participant ytdlp as yt-dlp
    participant ffmpeg as ffmpeg

    User->>Client: "Download this video as mp3"
    Client->>Server: JSON-RPC tool call:<br/>download_audio(url, format="mp3")
    Server->>Server: _quiet_opts() + _expand_dir()
    Server->>ytdlp: extract_info(url, download=True)
    ytdlp->>ytdlp: Download best audio stream
    ytdlp->>ffmpeg: Post-process: convert to mp3
    ffmpeg-->>ytdlp: mp3 file written
    ytdlp-->>Server: info dict with file path
    Server-->>Client: JSON response:<br/>{file_path, title, duration, video_id}
    Client-->>User: "Downloaded: Song.mp3"
```

## Frame Extraction Pipeline

```mermaid
sequenceDiagram
    participant Client as MCP Client
    participant Server as server.py
    participant ytdlp as yt-dlp
    participant ffmpeg as ffmpeg
    participant Disk as ~/Downloads

    Client->>Server: extract_key_frames(url, threshold=0.3)

    rect rgb(240, 248, 255)
        Note over Server,ffmpeg: Step 1: Download at 720p
        Server->>ytdlp: Download video (720p cap)
        ytdlp-->>Server: video.mp4 in temp dir
    end

    rect rgb(255, 248, 240)
        Note over Server,ffmpeg: Step 2: Detect scene changes
        Server->>ffmpeg: select='gt(scene,0.3)',showinfo
        ffmpeg-->>Server: List of timestamps
    end

    rect rgb(240, 255, 240)
        Note over Server,ffmpeg: Step 3: Extract frames
        loop For each timestamp
            Server->>ffmpeg: Extract JPEG frame at timestamp
            ffmpeg-->>Server: frame_NNNN.jpg
        end
    end

    rect rgb(255, 240, 255)
        Note over Server,Disk: Step 4 (optional): Save full-res
        alt output_dir provided
            Server->>ytdlp: Re-download at full resolution
            loop For each timestamp
                Server->>ffmpeg: Extract PNG frame
                ffmpeg-->>Disk: Full-res PNG saved
            end
        end
    end

    Server-->>Client: {frames: [{timestamp, base64_jpeg, file_path?}, ...]}
```

## Transcript Processing Flow

```mermaid
flowchart LR
    URL["Video URL"] --> YTDLP["yt-dlp downloads\nsubtitle files"]
    YTDLP --> VTT["Raw .vtt file"]

    subgraph strip["_strip_vtt() Processing"]
        direction TB
        S1["Remove headers\n(WEBVTT, Kind, Language, NOTE)"]
        S2["Remove timestamp lines\n(containing -->)"]
        S3["Remove cue IDs\n(numeric-only lines)"]
        S4["Strip HTML tags\n(<c>, </c>, etc.)"]
        S5["Deduplicate lines\n(seen set)"]
        S1 --> S2 --> S3 --> S4 --> S5
    end

    VTT --> strip
    strip --> TXT["Clean plain text"]
    TXT --> RES["Response:\n{text, language,\nsource, title, video_id}"]
```
