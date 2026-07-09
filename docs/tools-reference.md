# Tools Reference

The server exposes seven MCP tools. All tools accept a video URL (any site supported by yt-dlp) and return structured JSON responses.

---

## `get_transcript`

Fetch a video's captions as clean plain text.

Prefers manually uploaded subtitles. If none are available for the requested language, falls back to auto-generated captions.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `string` | *required* | Video URL |
| `language` | `string` | `"en"` | ISO 639-1 language code |

### Response

**Success:**

| Field | Type | Description |
|-------|------|-------------|
| `text` | `string` | Plain text transcript with duplicates removed and VTT markup stripped |
| `language` | `string` | Language code used |
| `source` | `string` | `"manual"` or `"auto"` |
| `title` | `string` | Video title |
| `video_id` | `string` | Video ID |

**No subtitles found:**

| Field | Type | Description |
|-------|------|-------------|
| `error` | `string` | Error message |
| `available_manual` | `list[string]` | Available manual subtitle languages |
| `available_auto` | `list[string]` | Available auto-generated subtitle languages |

### Example

```python
get_transcript(url="https://youtube.com/watch?v=dQw4w9WgXcQ", language="en")
```

---

## `extract_key_frames`

Auto-detect and capture visually significant moments using ffmpeg scene change detection. Ideal for videos with slides, diagrams, or visual topic shifts.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `string` | *required* | Video URL |
| `threshold` | `float` | `0.3` | Scene change sensitivity (0.0-1.0). Lower = more sensitive. Use `0.2` for dense/subtle content. |
| `max_frames` | `int` | `20` | Maximum number of frames to return |
| `min_gap` | `float` | `2.0` | Minimum seconds between detected scenes |
| `output_dir` | `string \| null` | `null` | If set, saves full-resolution PNG originals to this directory |

### Response

| Field | Type | Description |
|-------|------|-------------|
| `title` | `string` | Video title |
| `video_id` | `string` | Video ID |
| `duration_seconds` | `number` | Video duration |
| `frame_count` | `int` | Number of frames captured |
| `detection_threshold` | `float` | Threshold used |
| `min_gap_seconds` | `float` | Minimum gap used |
| `frames` | `list` | Array of frame entries (see below) |

**Frame entry:**

| Field | Type | Description |
|-------|------|-------------|
| `timestamp_seconds` | `float` | Timestamp in seconds |
| `timestamp` | `string` | Formatted timestamp (MM:SS or HH:MM:SS) |
| `base64_jpeg` | `string` | Base64-encoded JPEG image (720p) |
| `file_path` | `string` | Path to saved PNG file (only if `output_dir` was set) |

### Example

```python
extract_key_frames(url="https://youtube.com/watch?v=...", threshold=0.2, max_frames=10)
```

---

## `extract_frames`

Extract frames at regular time intervals. Useful for uniformly sampling visual content from a video.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `string` | *required* | Video URL |
| `interval_seconds` | `float` | `10.0` | Seconds between each frame capture |
| `max_frames` | `int` | `20` | Maximum number of frames to return |
| `output_dir` | `string \| null` | `null` | If set, saves full-resolution PNG originals to this directory |

### Response

Same as `extract_key_frames`, plus:

| Field | Type | Description |
|-------|------|-------------|
| `interval_seconds` | `float` | Interval that was used |

### Example

```python
extract_frames(url="https://youtube.com/watch?v=...", interval_seconds=30, max_frames=10)
```

---

## `snapshot`

Capture frames at specific user-supplied timestamps.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `string` | *required* | Video URL |
| `timestamps` | `list[string]` | *required* | List of timestamp strings |
| `output_dir` | `string \| null` | `null` | If set, saves full-resolution PNG originals to this directory |

Supported timestamp formats:
- `"90"` — seconds only
- `"1:30"` — MM:SS
- `"1:02:30"` — HH:MM:SS

### Response

Same structure as `extract_key_frames` (without `detection_threshold` and `min_gap_seconds`).

### Example

```python
snapshot(url="https://youtube.com/watch?v=...", timestamps=["0:30", "2:45", "1:02:30"])
```

---

## `download_subtitles`

Download subtitle files to disk.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `string` | *required* | Video URL |
| `language` | `string` | `"en"` | ISO 639-1 language code |
| `output_dir` | `string \| null` | `null` | Output directory (defaults to `~/Downloads`) |
| `subtitle_format` | `string` | `"vtt"` | `vtt`, `srt`, `ass`, or `json3` |
| `include_auto` | `bool` | `true` | Whether to include auto-generated subtitles |

### Response

| Field | Type | Description |
|-------|------|-------------|
| `file_paths` | `list[string]` | Paths to saved subtitle files |
| `title` | `string` | Video title |
| `video_id` | `string` | Video ID |

### Example

```python
download_subtitles(url="https://youtube.com/watch?v=...", subtitle_format="srt", language="en")
```

---

## `download_audio`

Download and convert audio using ffmpeg.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `string` | *required* | Video URL |
| `output_dir` | `string \| null` | `null` | Output directory (defaults to `~/Downloads`) |
| `audio_format` | `string` | `"mp3"` | `mp3`, `m4a`, `opus`, `wav`, or `flac` |
| `quality` | `string` | `"192"` | Bitrate for lossy codecs (e.g. `"192"`, `"320"`). Ignored for lossless formats. |

### Response

| Field | Type | Description |
|-------|------|-------------|
| `file_path` | `string \| null` | Path to the downloaded file |
| `title` | `string` | Video title |
| `duration_seconds` | `number` | Duration in seconds |
| `video_id` | `string` | Video ID |

### Example

```python
download_audio(url="https://youtube.com/watch?v=...", audio_format="flac")
```

---

## `download_video`

Download a video with optional resolution cap.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `string` | *required* | Video URL |
| `output_dir` | `string \| null` | `null` | Output directory (defaults to `~/Downloads`) |
| `max_height` | `int \| null` | `1080` | Maximum vertical resolution (e.g. `720`, `1080`). `null` for best available. |
| `container` | `string` | `"mp4"` | `mp4`, `mkv`, or `webm` |

### Response

| Field | Type | Description |
|-------|------|-------------|
| `file_path` | `string \| null` | Path to the downloaded file |
| `title` | `string` | Video title |
| `duration_seconds` | `number` | Duration in seconds |
| `resolution` | `string \| null` | Resolution string (e.g. `"1920x1080"`) |
| `video_id` | `string` | Video ID |

### Example

```python
download_video(url="https://youtube.com/watch?v=...", max_height=720, container="mkv")
```
