# X Fetcher Content Pipeline Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Turn `x-tweet-fetcher` into a portable package-based runtime that can ingest one X URL into a normalized portable content bundle on local disk, without introducing machine-bound path assumptions.

**Architecture:** Keep `x-tweet-fetcher` as the runtime repo and treat any content repo (including `link-vault`) as a later publish target. For this first milestone, lock the package scaffold, config model, normalized document schema, one X connector, and local bundle writing. Do not build search, target-repo sync, or GitHub Pages in this milestone.

**Tech Stack:** Python 3.10+, stdlib, pytest, existing script logic reused by extraction/refactor, local filesystem bundles.

---

## Scope of this plan

This plan is intentionally narrower than the architecture memo it replaces.

This milestone includes:
- package scaffold under `xfetch/`
- packaging via `pyproject.toml`
- config loading with portable default paths
- a locked `NormalizedDocument` schema
- deterministic slug generation
- one connector: X single-URL ingest happy path
- local bundle writing to `content-out/`
- tests for schema, slugs, bundle output, and X connector contract
- a minimal CLI entrypoint

This milestone does not include:
- target repo sync
- GitHub Pages publishing
- local search/vector DB
- ASR/faster-whisper
- YouTube, Bilibili, WeChat, or generic web connectors
- migration of all legacy scripts

Those come after this milestone is stable.

---

## Non-negotiable decisions

1. Runtime repo remains `x-tweet-fetcher`.
2. Content bundles are the durable cross-environment interface.
3. No shared mutable DB is required for correctness.
4. Any DB added later must be rebuildable from bundles.
5. All paths must be config-driven, not machine-hardcoded.
6. This milestone must work fully locally before any publish target exists.

---

## Current repo reality

Observed current state:
- repo is script-heavy under `scripts/`
- no `xfetch/` package exists yet
- no `tests/` directory exists yet
- no `pyproject.toml` exists yet
- `scripts/fetch_tweet.py` is a large monolith and must be sliced, not moved wholesale
- `scripts/fetch_china.py` already has parser abstractions but is out of scope for this milestone
- `scripts/common.py` contains reusable helpers, but only copy/extract what is needed now

Implication:
- do not try to “fully refactor” the repo in one pass
- build a clean package seam first, then migrate functionality behind it incrementally

---

## Milestone 1 acceptance criteria

This milestone is done when all of the following are true:

1. `python -m xfetch --help` works.
2. `python -m xfetch ingest <x-url>` writes a portable bundle under `content-out/`.
3. Bundle path and content do not depend on the local machine name or repo-relative hacks.
4. `document.json` follows the schema in this plan.
5. Slug generation is deterministic.
6. Tests pass locally with no network access by using fixtures/mocks.
7. Legacy scripts may still exist unchanged, but the new package is the preferred runtime path for this milestone.

Development note:
- run tests from the repo root
- editable install is only required at final verification time, not before Task 1

---

## Locked file plan for this milestone

### Create
- `pyproject.toml`
- `xfetch/__init__.py`
- `xfetch/__main__.py`
- `xfetch/cli.py`
- `xfetch/config.py`
- `xfetch/models.py`
- `xfetch/connectors/__init__.py`
- `xfetch/connectors/base.py`
- `xfetch/connectors/x.py`
- `xfetch/backends/__init__.py`
- `xfetch/backends/fxtwitter.py`
- `xfetch/pipeline/__init__.py`
- `xfetch/pipeline/bundle.py`
- `tests/test_cli.py`
- `tests/test_models.py`
- `tests/test_bundle.py`
- `tests/test_x_connector.py`
- `tests/fixtures/fxtwitter_single_tweet.json`

### Modify
- `README.md` (only after code passes; add package usage section)
- optionally `scripts/fetch_tweet.py` at the end of the milestone for a small note or compatibility bridge only if low-risk

### Do not touch in this milestone unless absolutely necessary
- `scripts/fetch_china.py`
- `scripts/common.py`
- search/index code that does not exist yet
- any publishing/target-repo sync implementation

---

## Migration map for this milestone

Use this exact migration boundary.

### From legacy scripts to package
- `scripts/fetch_tweet.py`
  - extract only the single-tweet FxTwitter fetch path into `xfetch/backends/fxtwitter.py`
  - do not migrate replies, monitor, list, article, or browser logic yet
- `scripts/config.py`
  - do not reuse directly
  - create a new package-native `xfetch/config.py` with runtime path settings for bundles
- `scripts/common.py`
  - do not import wholesale into runtime path
  - copy only tiny pure helpers if required and only into the right package module

### Explicitly postponed
- Camofox backend
- yt-dlp backend
- China platform connectors
- repo sync/publish targets
- DB/search layer

---

## Locked data model

The package must define a `NormalizedDocument` model. Use a dataclass, not ad hoc dicts.

### Required `NormalizedDocument` fields

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass(slots=True)
class NormalizedDocument:
    source_type: str                 # "x"
    source_url: str
    canonical_url: str
    external_id: str                 # tweet ID
    title: str                       # short derived title
    author: str                      # display name or screen name
    author_handle: str               # screen name without @
    created_at: str | None           # ISO 8601 when known
    language: str | None
    text: str                        # normalized searchable text
    markdown: str                    # human-readable rendering
    summary: str | None
    tags: list[str] = field(default_factory=list)
    assets: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    lineage: dict[str, Any] = field(default_factory=dict)
```

### Required `metadata` shape for X in this milestone

```python
{
    "platform": "x",
    "tweet_id": "1891234567890123456",
    "screen_name": "elonmusk",
    "display_name": "Elon Musk",
    "stats": {
        "likes": 123,
        "retweets": 45,
        "replies": 6,
        "views": 7890,
    },
    "raw_source": "fxtwitter",
}
```

### Required `lineage` shape in this milestone

```python
{
    "fetched_at": "2026-03-31T12:34:56Z",
    "connector": "x",
    "backend": "fxtwitter",
    "runtime_version": "0.1.0",
}
```

### Title derivation rule
- use first non-empty line of tweet text
- collapse whitespace
- trim to 80 chars
- if empty, use `X post <external_id>`

### Markdown rendering rule
Render markdown like:

```md
# {title}

- Source: {canonical_url}
- Author: @{author_handle}
- Created: {created_at or "unknown"}

{text}
```

Do not overdesign markdown in this milestone.

---

## Locked bundle contract

Bundle root:

```text
content-out/YYYY-MM/<slug>/
```

Required files per bundle:

```text
content-out/
  2026-03/
    x-1891234567890123456-elonmusk/
      document.json
      index.md
      publish.json
      assets/
```

### Slug rules
Slug format for this milestone:

```text
x-<external_id>-<author_handle>
```

Rules:
- lowercase only
- non `[a-z0-9-]` becomes `-`
- collapse repeated `-`
- trim leading/trailing `-`
- if author handle missing, use `unknown`

This milestone does not need fancy title-based slugs.

### `document.json`
Must contain serialized `NormalizedDocument`.

Do not store bundle-local metadata in `document.json`.
Specifically, `slug`, `bundle_dir`, and publish state belong in filesystem layout and `publish.json`, not in `document.json`.

### `index.md`
Must contain `NormalizedDocument.markdown`.

### `publish.json`
In this milestone, write a minimal placeholder document:

```json
{
  "published": false,
  "public_url": null,
  "target": null,
  "revision": null
}
```

### `assets/`
Must always exist, even if empty.

### Timestamp normalization rule
- normalize upstream timestamps to UTC ISO 8601 with trailing `Z`
- if timestamp conversion fails, set `created_at = None`

---

## Runtime config contract

Create `xfetch/config.py` with a dataclass `RuntimeConfig`.

Required fields:

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(slots=True)
class RuntimeConfig:
    content_root: Path
    site_root: Path
    timezone: str = "UTC"
    runtime_version: str = "0.1.0"
```

### Config loading precedence
1. explicit CLI args
2. env vars
3. repo-local defaults

### Required env vars for this milestone
- `XFETCH_CONTENT_ROOT`
- `XFETCH_SITE_ROOT`

### Default values for this repo
- `content_root = Path("content-out")`
- `site_root = Path("site-out")`

Resolve paths with `Path(...).expanduser().resolve()` at load time.

Do not add YAML/TOML config files in this milestone.

---

## CLI contract for this milestone

Support exactly one command path:

```bash
python -m xfetch ingest <url>
```

Optional flags:

```bash
python -m xfetch ingest <url> --content-root ./tmp-content
python -m xfetch ingest <url> --json
```

Behavior:
- detect X URL
- fetch through X connector
- write bundle
- print either bundle path or JSON summary

JSON summary shape:

```json
{
  "ok": true,
  "source_type": "x",
  "external_id": "1891234567890123456",
  "bundle_dir": "/abs/path/to/content-out/2026-03/x-1891234567890123456-elonmusk"
}
```

Out of scope:
- ingesting non-X URLs
- batch ingest
- publish subcommands

---

## Connector/backend boundary

Lock this boundary now.

### Connector
A connector:
- knows source-specific URL matching
- calls one or more backends
- normalizes source output into `NormalizedDocument`
- does not write files directly

### Backend
A backend:
- performs raw fetch/transport
- returns raw source-shaped data or a tiny backend DTO
- does not know bundle layout
- does not know publish logic

For this milestone:
- `xfetch/connectors/x.py` = connector
- `xfetch/backends/fxtwitter.py` = backend

---

## Testing rules

1. No live network in tests.
2. Use a recorded fixture representing a single FxTwitter response.
   - derive this fixture from the currently working single-tweet path in `scripts/fetch_tweet.py`
   - do not invent a new third-party payload shape by hand
3. Test the connector contract, not the third-party service.
4. Test deterministic slugs directly.
5. Test exact bundle file layout.
6. Test CLI smoke path with monkeypatched connector/backend.
7. Test unsupported URL handling explicitly.

---

## Task 1: Add packaging scaffold

**Objective:** Make the repo installable and runnable as `python -m xfetch`.

**Files:**
- Create: `pyproject.toml`
- Create: `xfetch/__init__.py`
- Create: `xfetch/__main__.py`
- Create: `xfetch/cli.py`
- Test: `tests/test_cli.py`

**Step 1: Write failing CLI smoke test**

```python
from xfetch.cli import build_parser


def test_build_parser_exposes_ingest_command():
    parser = build_parser()
    args = parser.parse_args(["ingest", "https://x.com/a/status/1"])
    assert args.command == "ingest"
    assert args.url == "https://x.com/a/status/1"
```

**Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'xfetch'`

**Step 3: Add minimal packaging files**

Use this `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "x-tweet-fetcher"
version = "0.1.0"
description = "Portable content-ingestion runtime for X and related sources"
readme = "README.md"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Use this `xfetch/__init__.py`:

```python
__all__ = ["__version__"]
__version__ = "0.1.0"
```

Use this `xfetch/__main__.py`:

```python
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

Use this minimal parser in `xfetch/cli.py`:

```python
import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xfetch")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest")
    ingest.add_argument("url")
    ingest.add_argument("--content-root")
    ingest.add_argument("--json", action="store_true")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    return 0
```

**Step 4: Run test to verify pass**

Run: `python -m pytest tests/test_cli.py -q`
Expected: PASS

**Step 5: Verify module entrypoint**

Run: `python -m xfetch --help`
Expected: shows `ingest` subcommand

**Step 6: Commit**

```bash
git add pyproject.toml xfetch/__init__.py xfetch/__main__.py xfetch/cli.py tests/test_cli.py
git commit -m "feat: add xfetch package scaffold and cli shell"
```

---

## Task 2: Add runtime config

**Objective:** Introduce portable runtime path config with explicit precedence and sane defaults.

**Files:**
- Create: `xfetch/config.py`
- Modify: `xfetch/cli.py`
- Test: `tests/test_cli.py`

**Step 1: Write failing config test**

Add to `tests/test_cli.py`:

```python
from xfetch.config import load_config


def test_load_config_prefers_explicit_content_root(tmp_path, monkeypatch):
    monkeypatch.setenv("XFETCH_CONTENT_ROOT", "/tmp/wrong")
    cfg = load_config(content_root=tmp_path)
    assert cfg.content_root == tmp_path.resolve()


def test_load_config_uses_repo_local_defaults_when_no_args_or_env(monkeypatch):
    monkeypatch.delenv("XFETCH_CONTENT_ROOT", raising=False)
    monkeypatch.delenv("XFETCH_SITE_ROOT", raising=False)
    cfg = load_config()
    assert cfg.content_root.name == "content-out"
    assert cfg.site_root.name == "site-out"
```

**Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_cli.py -q`
Expected: FAIL with missing import or missing function

**Step 3: Add `xfetch/config.py`**

```python
from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(slots=True)
class RuntimeConfig:
    content_root: Path
    site_root: Path
    timezone: str = "UTC"
    runtime_version: str = "0.1.0"


def _resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def load_config(content_root: str | Path | None = None, site_root: str | Path | None = None) -> RuntimeConfig:
    raw_content = content_root or os.environ.get("XFETCH_CONTENT_ROOT") or "content-out"
    raw_site = site_root or os.environ.get("XFETCH_SITE_ROOT") or "site-out"
    return RuntimeConfig(
        content_root=_resolve_path(raw_content),
        site_root=_resolve_path(raw_site),
    )
```

Then wire `xfetch/cli.py` to call `load_config(...)` in the ingest path, even if ingest logic is still placeholder.

**Step 4: Run tests**

Run: `python -m pytest tests/test_cli.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add xfetch/config.py xfetch/cli.py tests/test_cli.py
git commit -m "feat: add runtime config loading"
```

---

## Task 3: Add normalized document model

**Objective:** Lock the internal schema before writing connector or bundle code.

**Files:**
- Create: `xfetch/models.py`
- Test: `tests/test_models.py`

**Step 1: Write failing tests for schema and title fallback**

```python
from xfetch.models import NormalizedDocument, derive_title


def test_derive_title_uses_first_line_and_trims():
    text = "First line here\nSecond line"
    assert derive_title(text, "123") == "First line here"


def test_derive_title_falls_back_to_external_id_when_text_empty():
    assert derive_title("   ", "123") == "X post 123"
```

**Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_models.py -q`
Expected: FAIL

**Step 3: Implement schema**

Required helpers in `xfetch/models.py`:
- `derive_title(text: str, external_id: str) -> str`
- `render_markdown(doc: NormalizedDocument) -> str`
- `document_to_dict(doc: NormalizedDocument) -> dict`

Use a dataclass exactly matching the locked model above.

**Step 4: Add one serialization test**

```python
from xfetch.models import NormalizedDocument, document_to_dict


def test_document_to_dict_preserves_required_fields():
    doc = NormalizedDocument(
        source_type="x",
        source_url="https://x.com/a/status/1",
        canonical_url="https://x.com/a/status/1",
        external_id="1",
        title="hello",
        author="alice",
        author_handle="alice",
        created_at=None,
        language=None,
        text="hello",
        markdown="# hello",
        summary=None,
    )
    data = document_to_dict(doc)
    assert data["source_type"] == "x"
    assert data["external_id"] == "1"
```

**Step 5: Run tests**

Run: `python -m pytest tests/test_models.py -q`
Expected: PASS

**Step 6: Commit**

```bash
git add xfetch/models.py tests/test_models.py
git commit -m "feat: add normalized document model"
```

---

## Task 4: Add bundle writer

**Objective:** Serialize normalized documents into deterministic portable bundles.

**Files:**
- Create: `xfetch/pipeline/__init__.py`
- Create: `xfetch/pipeline/bundle.py`
- Test: `tests/test_bundle.py`

**Step 1: Write failing bundle tests**

```python
from xfetch.config import RuntimeConfig
from xfetch.models import NormalizedDocument
from xfetch.pipeline.bundle import build_slug, bundle_month, write_bundle


def test_build_slug_uses_external_id_and_handle():
    assert build_slug("x", "123", "Elon_Musk") == "x-123-elon-musk"


def test_bundle_month_falls_back_to_fetched_at_when_created_at_missing():
    assert bundle_month(None, "2026-03-31T12:34:56Z") == "2026-03"


def test_write_bundle_creates_expected_files(tmp_path):
    cfg = RuntimeConfig(content_root=tmp_path, site_root=tmp_path / "site")
    doc = NormalizedDocument(
        source_type="x",
        source_url="https://x.com/a/status/123",
        canonical_url="https://x.com/a/status/123",
        external_id="123",
        title="hello",
        author="alice",
        author_handle="alice",
        created_at="2026-03-31T00:00:00Z",
        language=None,
        text="hello",
        markdown="# hello",
        summary=None,
    )
    bundle_dir = write_bundle(doc, cfg)
    assert (bundle_dir / "document.json").exists()
    assert (bundle_dir / "index.md").exists()
    assert (bundle_dir / "publish.json").exists()
    assert (bundle_dir / "assets").is_dir()
```

**Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_bundle.py -q`
Expected: FAIL

**Step 3: Implement bundle code**

`xfetch/pipeline/bundle.py` must expose:
- `slugify(text: str) -> str`
- `build_slug(source_type: str, external_id: str, author_handle: str | None) -> str`
- `bundle_month(created_at: str | None, fetched_at: str | None = None) -> str`
- `write_bundle(doc: NormalizedDocument, config: RuntimeConfig) -> Path`

Rules:
- if `created_at` is present and parseable, month folder comes from it
- else use current UTC fetch month
- ensure parent directories exist
- JSON files are UTF-8, `ensure_ascii=False`, `indent=2`

**Step 4: Run tests**

Run: `python -m pytest tests/test_bundle.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add xfetch/pipeline/__init__.py xfetch/pipeline/bundle.py tests/test_bundle.py
git commit -m "feat: add bundle writer"
```

---

## Task 5: Add FxTwitter backend

**Objective:** Add a narrow backend that fetches one X post’s raw data without bundle or CLI concerns.

**Files:**
- Create: `xfetch/backends/__init__.py`
- Create: `xfetch/backends/fxtwitter.py`
- Test: `tests/test_x_connector.py`
- Fixture: `tests/fixtures/fxtwitter_single_tweet.json`

**Step 1: Write failing backend-shape test**

```python
from pathlib import Path
import json
from xfetch.backends.fxtwitter import parse_fxtwitter_payload


def test_parse_fxtwitter_payload_extracts_minimum_fields():
    payload = json.loads(Path("tests/fixtures/fxtwitter_single_tweet.json").read_text())
    raw = parse_fxtwitter_payload(payload)
    assert raw["tweet_id"]
    assert raw["screen_name"]
    assert raw["text"]
```

**Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_x_connector.py -q`
Expected: FAIL

**Step 3: Implement backend narrowly**

`xfetch/backends/fxtwitter.py` must expose:
- `build_fxtwitter_url(tweet_url: str) -> str`
- `fetch_fxtwitter_json(tweet_url: str, timeout: int = 20) -> dict`
- `parse_fxtwitter_payload(payload: dict) -> dict`

`parse_fxtwitter_payload()` should return a small raw dict shaped like:

```python
{
    "tweet_id": "123",
    "canonical_url": "https://x.com/user/status/123",
    "screen_name": "user",
    "display_name": "User Name",
    "text": "tweet text",
    "created_at": "2026-03-31T00:00:00Z",
    "language": None,
    "stats": {
        "likes": 1,
        "retweets": 2,
        "replies": 3,
        "views": 4,
    },
    "media": [],
}
```

Do not leak raw third-party response shape beyond this module.

Timestamp handling rule for this backend:
- convert upstream timestamps to UTC ISO 8601 with trailing `Z`
- if conversion fails, return `created_at = None`

**Step 4: Record one fixture**

Add `tests/fixtures/fxtwitter_single_tweet.json` from a representative successful payload. Redact anything unnecessary. Keep only one stable sample.

**Step 5: Run tests**

Run: `python -m pytest tests/test_x_connector.py -q`
Expected: PASS for backend parse test

**Step 6: Commit**

```bash
git add xfetch/backends/__init__.py xfetch/backends/fxtwitter.py tests/test_x_connector.py tests/fixtures/fxtwitter_single_tweet.json
git commit -m "feat: add fxtwitter backend"
```

---

## Task 6: Add X connector

**Objective:** Convert raw X backend output into the locked normalized document contract.

**Files:**
- Create: `xfetch/connectors/__init__.py`
- Create: `xfetch/connectors/base.py`
- Create: `xfetch/connectors/x.py`
- Test: `tests/test_x_connector.py`

**Step 1: Write failing connector normalization test**

```python
from pathlib import Path
import json
from xfetch.connectors.x import XConnector


def test_x_connector_normalizes_fixture_payload():
    payload = json.loads(Path("tests/fixtures/fxtwitter_single_tweet.json").read_text())
    connector = XConnector()
    doc = connector.normalize_payload(
        source_url="https://x.com/alice/status/123",
        payload=payload,
    )
    assert doc.source_type == "x"
    assert doc.external_id == "123"
    assert doc.author_handle == "alice"
    assert doc.metadata["platform"] == "x"
    assert doc.lineage["backend"] == "fxtwitter"
```

**Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_x_connector.py -q`
Expected: FAIL

**Step 3: Implement connector boundary**

`xfetch/connectors/base.py`:

```python
from abc import ABC, abstractmethod
from xfetch.models import NormalizedDocument


class BaseConnector(ABC):
    @abstractmethod
    def can_handle(self, url: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def fetch(self, url: str) -> NormalizedDocument:
        raise NotImplementedError
```

`xfetch/connectors/x.py` must expose:
- `is_x_url(url: str) -> bool`
- `XConnector`
- `XConnector.fetch(url: str) -> NormalizedDocument`
- `XConnector.normalize_payload(source_url: str, payload: dict) -> NormalizedDocument`

Rules:
- `can_handle()` accepts `x.com` and `twitter.com`
- use `parse_fxtwitter_payload()` internally
- construct markdown via `render_markdown()`
- set `lineage["connector"] = "x"`
- set `lineage["backend"] = "fxtwitter"`
- set `lineage["runtime_version"] = "0.1.0"`

**Step 4: Run tests**

Run: `python -m pytest tests/test_x_connector.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add xfetch/connectors/__init__.py xfetch/connectors/base.py xfetch/connectors/x.py tests/test_x_connector.py
git commit -m "feat: add x connector"
```

---

## Task 7: Wire CLI ingest path end-to-end

**Objective:** Make `python -m xfetch ingest <url>` fetch and write a bundle.

**Files:**
- Modify: `xfetch/cli.py`
- Test: `tests/test_cli.py`

**Step 1: Write failing end-to-end CLI unit test with monkeypatch**

```python
from xfetch.cli import main
from xfetch.models import NormalizedDocument


def test_cli_ingest_writes_bundle(tmp_path, monkeypatch):
    doc = NormalizedDocument(
        source_type="x",
        source_url="https://x.com/alice/status/123",
        canonical_url="https://x.com/alice/status/123",
        external_id="123",
        title="hello",
        author="alice",
        author_handle="alice",
        created_at="2026-03-31T00:00:00Z",
        language=None,
        text="hello",
        markdown="# hello",
        summary=None,
    )

    class FakeConnector:
        def fetch(self, url):
            return doc

    monkeypatch.setattr("xfetch.cli.pick_connector", lambda url: FakeConnector())
    rc = main(["ingest", "https://x.com/alice/status/123", "--content-root", str(tmp_path)])
    assert rc == 0


def test_cli_returns_2_for_unsupported_url(tmp_path):
    rc = main(["ingest", "https://example.com/post/123", "--content-root", str(tmp_path)])
    assert rc == 2
```

**Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_cli.py -q`
Expected: FAIL

**Step 3: Implement CLI flow**

`xfetch/cli.py` must expose:
- `pick_connector(url: str)`
- `run_ingest(args) -> int`
- `main(argv=None) -> int`

Flow:
1. parse args
2. load config
3. pick X connector for supported URL
4. fetch normalized doc
5. write bundle
6. print path or JSON summary
7. return `0` on success, `2` on unsupported URL

**Step 4: Run tests**

Run: `python -m pytest tests/test_cli.py tests/test_models.py tests/test_bundle.py tests/test_x_connector.py -q`
Expected: all PASS

**Step 5: Manual smoke test**

Run: `python -m xfetch --help`
Expected: CLI help renders

Optional live test only if you want to verify network path manually:

```bash
python -m xfetch ingest "https://x.com/jack/status/20"
```

Do not make CI/tests depend on live network.

**Step 6: Commit**

```bash
git add xfetch/cli.py tests/test_cli.py
git commit -m "feat: wire cli ingest flow"
```

---

## Task 8: Add README section for the new runtime path

**Objective:** Make the package entrypoint discoverable without claiming full migration is complete.

**Files:**
- Modify: `README.md`

**Step 1: Add a short “New package runtime (milestone 1)” section**

Include exactly these commands:

```bash
pip install -e .[dev]
python -m xfetch --help
python -m xfetch ingest "https://x.com/jack/status/20"
```

State clearly:
- current package scope is single X URL -> local bundle
- legacy scripts remain for broader features during migration

**Step 2: Verify README does not promise features not yet ported**

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add package runtime usage"
```

---

## Final verification checklist

Run all of these from repo root:

```bash
python -m pip install -e .[dev]
python -m pytest -q
python -m xfetch --help
```

Expected:
- editable install succeeds
- all tests pass
- CLI help renders

Then verify bundle layout using a monkeypatched or live ingest:

```bash
python -m xfetch ingest "https://x.com/jack/status/20"
find content-out -maxdepth 3 -type f | sort
```

Expected files under one bundle dir:
- `document.json`
- `index.md`
- `publish.json`

---

## Follow-on milestone plan stub

Only start these after this milestone is merged and stable:

1. Add target repo sync abstraction
2. Add GitHub Pages/public URL support
3. Add yt-dlp backend and media asset capture
4. Add faster-whisper transcription pipeline
5. Add YouTube and one non-X connector
6. Add runtime-local rebuildable index/DB
7. Wrap legacy scripts around package APIs where useful

---

## Execution handoff

This file is now intended to be implementation-ready for milestone 1 only.

Start in `/Users/zion/x-tweet-fetcher`.
Implement the tasks in order.
Do not expand scope mid-flight.
Do not add publishing, DB, or ASR work before the local bundle path is stable.
