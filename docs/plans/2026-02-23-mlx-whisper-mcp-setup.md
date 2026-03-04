# x-reader: mlx-whisper + MCP Setup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Set up x-reader as a Claude Code MCP server with local mlx-whisper transcription (primary) and Groq Whisper (fallback).

**Architecture:** Install prerequisites (ffmpeg, yt-dlp, mlx-whisper), modify youtube.py to try local transcription first before hitting the Groq API, then register the MCP server in Claude Code settings. Groq remains as fallback for resilience.

**Tech Stack:** Python 3.12, mlx-whisper (Apple Silicon MLX), yt-dlp, ffmpeg, Groq Whisper API (fallback), FastMCP (stdio transport)

---

## Task 1: Install system prerequisites

**Files:** none

**Step 1: Install ffmpeg and yt-dlp via Homebrew**

```bash
brew install ffmpeg yt-dlp
```

Expected: both install without errors.

**Step 2: Verify**

```bash
ffmpeg -version | head -1
yt-dlp --version
```

Expected: version strings printed.

**Step 3: Commit** — none (system installs, not code changes)

---

## Task 2: Install x-reader Python package with dependencies

**Files:** none

**Step 1: Install x-reader with mcp extras into miniconda**

```bash
cd ~/projects/x-reader
pip install -e ".[mcp,browser]"
```

Expected: package installs in editable mode.

**Step 2: Install mlx-whisper**

```bash
pip install mlx-whisper
```

Expected: installs without errors. This pulls Apple MLX framework automatically.

**Step 3: Verify mlx-whisper import**

```bash
python3 -c "import mlx_whisper; print('mlx_whisper ok')"
```

Expected: `mlx_whisper ok`

**Step 4: Verify mcp import**

```bash
python3 -c "from mcp.server.fastmcp import FastMCP; print('mcp ok')"
```

Expected: `mcp ok`

---

## Task 3: Create .env file with credentials

**Files:**
- Create: `~/projects/x-reader/.env`

**Step 1: Create .env from example**

```bash
cp ~/projects/x-reader/.env.example ~/projects/x-reader/.env
```

**Step 2: Set GROQ_API_KEY in .env**

Edit `~/projects/x-reader/.env` — add your Groq key:

```
GROQ_API_KEY=<your_groq_key_here>
OUTPUT_DIR=~/projects/x-reader/output
INBOX_FILE=~/projects/x-reader/unified_inbox.json
```

**Step 3: Add USE_LOCAL_WHISPER setting to .env**

```
# Local transcription (mlx-whisper, Apple Silicon)
USE_LOCAL_WHISPER=true
MLX_WHISPER_MODEL=mlx-community/whisper-large-v3-mlx
```

---

## Task 4: Add mlx-whisper optional dependency to pyproject.toml

**Files:**
- Modify: `~/projects/x-reader/pyproject.toml`

**Step 1: Read current pyproject.toml**

Open and read `pyproject.toml` to find the `[project.optional-dependencies]` section.

**Step 2: Add mlx dependency group**

In `[project.optional-dependencies]`, add:

```toml
mlx = ["mlx-whisper>=0.4"]
all = ["telethon>=1.34", "playwright>=1.40", "mcp[cli]>=1.0", "mlx-whisper>=0.4"]
```

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add mlx-whisper as optional dependency"
```

---

## Task 5: Modify youtube.py — add mlx-whisper local transcription

**Files:**
- Modify: `~/projects/x-reader/x_reader/fetchers/youtube.py`

This is the core change. The current `_transcribe_via_whisper()` calls Groq directly. We add a `_transcribe_local()` function that uses mlx-whisper, and update the pipeline to try local first.

**Step 1: Read current youtube.py in full**

Read `~/projects/x-reader/x_reader/fetchers/youtube.py` to understand exact line numbers and imports.

**Step 2: Add local transcription function**

After the existing imports, add:

```python
import os

def _transcribe_local(audio_path: str) -> str:
    """Transcribe audio using mlx-whisper on Apple Silicon. Returns transcript or empty string."""
    try:
        import mlx_whisper
        model = os.getenv("MLX_WHISPER_MODEL", "mlx-community/whisper-large-v3-mlx")
        logger.info(f"[youtube] transcribing locally with {model}")
        result = mlx_whisper.transcribe(audio_path, path_or_hf_repo=model)
        text = result.get("text", "").strip()
        logger.info(f"[youtube] local transcription done, {len(text)} chars")
        return text
    except Exception as e:
        logger.warning(f"[youtube] local transcription failed: {e}")
        return ""
```

**Step 3: Update `_transcribe_via_whisper()` to try local first**

Find the `_transcribe_via_whisper(url)` function. Before the Groq API call block, add local transcription attempt:

```python
def _transcribe_via_whisper(url: str) -> str:
    """Download audio and transcribe. Tries mlx-whisper locally first, falls back to Groq."""
    # ... existing audio download logic stays unchanged ...

    # After audio file is downloaded to `audio_path`, add:
    use_local = os.getenv("USE_LOCAL_WHISPER", "false").lower() == "true"
    if use_local:
        transcript = _transcribe_local(audio_path)
        if transcript:
            return transcript
        logger.info("[youtube] local transcription empty, falling back to Groq")

    # ... existing Groq API call continues unchanged as fallback ...
```

The exact insertion point depends on the line structure — read the file first in Step 1.

**Step 4: Verify syntax**

```bash
python3 -c "from x_reader.fetchers.youtube import fetch_youtube; print('ok')"
```

Expected: `ok`

**Step 5: Commit**

```bash
git add x_reader/fetchers/youtube.py
git commit -m "feat: add mlx-whisper local transcription with Groq fallback"
```

---

## Task 6: Update .env.example to document new settings

**Files:**
- Modify: `~/projects/x-reader/.env.example`

**Step 1: Add mlx-whisper section**

Append to `.env.example`:

```
# === Local Whisper (Apple Silicon, mlx-whisper) ===
# Set to true to use local transcription (no API key needed, runs on GPU)
# Falls back to GROQ_API_KEY if local transcription fails or returns empty
USE_LOCAL_WHISPER=true
MLX_WHISPER_MODEL=mlx-community/whisper-large-v3-mlx
```

**Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: document mlx-whisper env vars"
```

---

## Task 7: Register MCP server in Claude Code settings

**Files:**
- Modify: `~/.claude/settings.json`

**Step 1: Read current settings.json**

Read `~/.claude/settings.json` to understand current structure.

**Step 2: Add mcpServers block**

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "x-reader": {
      "command": "/Users/zion/miniconda3/bin/python",
      "args": ["/Users/zion/projects/x-reader/mcp_server.py"],
      "env": {
        "PYTHONPATH": "/Users/zion/projects/x-reader"
      }
    }
  }
}
```

Use the full miniconda Python path to ensure all installed packages are available.

**Step 3: Verify mcp_server.py runs**

```bash
cd ~/projects/x-reader && timeout 3 python mcp_server.py 2>&1 || true
```

Expected: server starts (may hang waiting for stdio — that's correct behavior).

---

## Task 8: Smoke test the MCP server

**Step 1: Test x-reader CLI directly**

```bash
cd ~/projects/x-reader
python -m x_reader.cli https://www.bbc.com/news 2>&1 | head -20
```

Expected: fetches and prints content from BBC.

**Step 2: Test platform detection**

```bash
python3 -c "
from x_reader.reader import UniversalReader
r = UniversalReader()
print(r._detect_platform('https://www.youtube.com/watch?v=dQw4w9WgXcQ'))
print(r._detect_platform('https://twitter.com/user/status/123'))
print(r._detect_platform('https://mp.weixin.qq.com/s/abc'))
"
```

Expected: `youtube`, `twitter`, `wechat`

**Step 3: Test a real URL fetch (non-video, no API needed)**

```bash
python3 -c "
import asyncio
from x_reader.reader import UniversalReader

async def test():
    r = UniversalReader()
    content = await r.read('https://feeds.bbci.co.uk/news/rss.xml')
    print(content.title[:80])
    print(content.source_type)

asyncio.run(test())
"
```

Expected: prints an RSS item title and `SourceType.rss`.

**Step 4: Restart Claude Code and verify MCP tools appear**

After restarting, check that `x-reader` tools are available (read_url, read_batch, list_inbox, detect_platform).

---

## Task 9: Push changes to fork

**Step 1: Review all changes**

```bash
cd ~/projects/x-reader && git log --oneline -5
```

**Step 2: Push to fork**

```bash
git push origin main
```

---

## Done

After Task 9, you have:
- `~/projects/x-reader` — modified fork with local mlx-whisper transcription
- MCP server registered in Claude Code — restart to activate
- Groq as fallback if local transcription fails
- First model download happens automatically on first video transcription (~1.5GB for whisper-large-v3-mlx)
