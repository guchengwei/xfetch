# xfetch

Chat-first link preservation runtime.

xfetch ingests a supported URL, normalizes it into a portable content bundle, and can sync/publish that bundle into a separate content repo for durable public hosting.

Current supported source families:
- X
- generic web pages
- RSS/Atom feeds
- public Telegram posts/channels
- WeChat articles
- Xiaohongshu notes
- YouTube videos
- Bilibili videos

Why xfetch exists:
- preserve content, not just bookmark links
- keep runtime code separate from published content artifacts
- work cleanly behind Hermes or other agent/chat front doors
- produce portable bundles that can be moved, synced, and published anywhere

Project note:
- this project previously lived under legacy names like x-reader / x-tweet-fetcher
- the intended identity now is xfetch

## What xfetch does

For each supported URL, xfetch can:
1. detect the right connector
2. fetch and normalize the source into a common document shape
3. write a local bundle directory
4. render a static HTML page for publication
5. sync/publish that bundle into a separate target repo
6. return a durable GitHub Pages URL

In practice, xfetch is the runtime layer in a larger flow:
- Hermes or another caller receives a natural-language save request
- xfetch ingests the URL and writes a normalized bundle
- xfetch syncs/publishes the bundle into a clean content repo
- GitHub Pages serves the rendered artifact

## Repo roles

xfetch intentionally separates runtime from content storage.

- xfetch repo
  - ingestion runtime
  - connectors
  - bundle writer
  - rendering logic
  - sync/publish commands

- link-vault repo
  - clean published artifact store
  - GitHub Pages surface
  - public item pages and homepage index

That split keeps code history and content history independent, and makes it easier to run ingestion in one environment while publishing in another.

## End-to-end architecture

```text
Hermes request
  -> xfetch ingest
  -> normalized bundle written locally
  -> xfetch sync/publish into target repo
  -> target repo push
  -> GitHub Pages serves rendered page
```

Current operational path on this machine:

```text
Hermes
  -> xfetch
  -> /Users/zion/link-vault-publish
  -> guchengwei/link-vault
  -> https://guchengwei.github.io/link-vault/
```

## Bundle contract

Each saved item is written as a portable bundle directory.

Typical structure:

```text
content-out/YYYY-MM/<slug>/
  document.json
  index.md
  publish.json
  assets/
```

Bundle files:
- document.json
  - normalized structured record
  - source metadata, title, author, timestamps, content fields, lineage
- index.md
  - markdown rendering of the captured content
- publish.json
  - publish state, target metadata, public URL, revision
- assets/
  - downloaded inline media when present

When published, xfetch also renders a static HTML page into the target repo's site tree so GitHub Pages can serve it directly.

## CLI

Install locally:

```bash
pip install -e .[dev]
python -m xfetch --help
```

Primary commands:
- ingest
- sync
- publish

### 1) Ingest

Ingest writes a local normalized bundle.

```bash
python -m xfetch ingest "https://x.com/jack/status/20"
python -m xfetch ingest "https://example.com/posts/123"
python -m xfetch ingest "https://example.com/feed.xml"
python -m xfetch ingest "https://t.me/ai_daily/123"
python -m xfetch ingest "https://mp.weixin.qq.com/s/example"
python -m xfetch ingest "https://www.xiaohongshu.com/explore/67b8e3f5000000000b00d8e2"
python -m xfetch ingest "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
python -m xfetch ingest "https://www.bilibili.com/video/BV1xx411c7mD"
```

Optional JSON output:

```bash
python -m xfetch ingest "https://x.com/jack/status/20" --json
```

If needed, you can override where bundles are written:

```bash
python -m xfetch ingest "https://x.com/jack/status/20" --content-root ./content-out
```

### 2) Sync

Sync copies a bundle and its rendered site output into a target repo working tree, but does not commit or push.

```bash
python -m xfetch sync ./content-out/2006-03/x-20-jack \
  --target-repo /Users/zion/link-vault-publish \
  --repo-owner guchengwei \
  --repo-name link-vault
```

### 3) Publish

Publish performs the sync, updates publish metadata, commits the target repo, and pushes it.

```bash
python -m xfetch publish ./content-out/2006-03/x-20-jack \
  --target-repo /Users/zion/link-vault-publish \
  --repo-owner guchengwei \
  --repo-name link-vault
```

Publish assumptions:
- the target repo already exists locally
- the target repo already has git remote/auth configured
- GitHub Pages deployment happens downstream in GitHub Actions after push
- xfetch renders static site output locally; the Pages workflow serves that output rather than re-running ingestion remotely

## Output and publication model

xfetch is designed around portable local-first artifacts.

What gets produced locally:
- a normalized bundle under content-out/
- a rendered static page for that bundle
- publish metadata recording the intended target and resulting public URL

What gets stored in the target content repo:
- copied bundle under content/
- rendered page under site/
- any copied assets needed for public serving

What becomes public:
- per-item GitHub Pages URL, typically:
  - https://guchengwei.github.io/link-vault/d/<slug>/
- homepage index in the publish repo, currently:
  - https://guchengwei.github.io/link-vault/

## Supported connector families

xfetch currently includes connectors for:
- x
- rss
- telegram
- wechat
- xiaohongshu
- youtube
- bilibili
- web

These all normalize into the same bundle contract, which lets downstream rendering and publication stay source-agnostic.

## Design principles

- chat-first
  - works well when invoked by Hermes or another agent
- portable bundles
  - saved items should remain useful outside the runtime that created them
- runtime/content separation
  - code repo and content repo should not be tightly coupled
- local rendering, remote serving
  - rendering happens locally; GitHub Pages serves prepared artifacts
- incremental source expansion
  - new connectors should plug into the same normalized document + bundle pipeline

## Development

Run targeted tests:

```bash
pytest tests/test_cli.py tests/test_publishing.py tests/test_render.py -q
```

Run the whole suite:

```bash
pytest -q
```

## Status

xfetch is the active save/publish runtime.

Legacy lineage from x-reader/x-tweet-fetcher still shows up in some history and packaging details, but the active direction is:
- xfetch as the runtime
- link-vault as the published artifact repo
- Hermes as the preferred chat interface

## Example mental model

A useful shorthand is:
- Karakeep manages a bookmark library
- xfetch preserves and publishes an individual item well

So xfetch is not trying to be a full bookmark-management product. It is the lean ingestion, normalization, and publication layer behind a preservation workflow.
