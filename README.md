# xfetch

Chat-first link preservation runtime.

xfetch turns supported public URLs into portable content bundles and can publish those bundles into a separate content repository for durable static hosting. It is intentionally focused: xfetch is a capture/preservation engine, not a universal reader, inbox, MCP product, search tool, or analysis suite.

## Install as a Codex or Claude Code skill

The installer supports macOS, Linux, and WSL. Start with a clean environment that has Codex or Claude Code installed and either `curl` or `wget`; it bootstraps a user-local `uv`/Python 3.12 runtime when needed. It does not require Git, global `pip`, `sudo`, or shell-profile edits. It resolves one immutable source revision and uses the same archive for the runtime and skill.

Download the installer before running it so a network failure cannot turn into a successful empty shell script. Set `XFETCH_AGENT` to the host where the skill should be installed:

```bash
XFETCH_AGENT=codex  # use claude for Claude Code, or both for both hosts
XFETCH_INSTALL_SCRIPT="$(mktemp)"
curl -fsSL https://raw.githubusercontent.com/guchengwei/xfetch/main/scripts/install.sh -o "$XFETCH_INSTALL_SCRIPT" &&
  sh "$XFETCH_INSTALL_SCRIPT" --agent "$XFETCH_AGENT"
XFETCH_INSTALL_STATUS=$?
rm -f -- "$XFETCH_INSTALL_SCRIPT"
test "$XFETCH_INSTALL_STATUS" -eq 0
```

If `curl` is unavailable, use `wget` for the download step:

```bash
XFETCH_AGENT=codex  # use claude or both as above
XFETCH_INSTALL_SCRIPT="$(mktemp)"
wget -qO "$XFETCH_INSTALL_SCRIPT" https://raw.githubusercontent.com/guchengwei/xfetch/main/scripts/install.sh &&
  sh "$XFETCH_INSTALL_SCRIPT" --agent "$XFETCH_AGENT"
XFETCH_INSTALL_STATUS=$?
rm -f -- "$XFETCH_INSTALL_SCRIPT"
test "$XFETCH_INSTALL_STATUS" -eq 0
```

The installer keeps the runtime under `~/.local/share/xfetch`, copies the skill to `~/.agents/skills/xfetch` for Codex and/or `~/.claude/skills/xfetch` for Claude Code, and writes `INSTALLATION.md` beside each installed `SKILL.md`. That file records the absolute executable path, the default `~/xfetch-content` archive location, and the installed revision. The managed runtime records its revision and executable checksum in `.xfetch-runtime`. The skill uses the recorded executable directly, so it works from any directory without activating a virtual environment or adding a directory to `PATH`.

To let an agent perform the installation, give it this request and select the intended host explicitly:

```text
Install xfetch for [Codex / Claude Code / both] by following the installation instructions at https://github.com/guchengwei/xfetch#install-as-a-codex-or-claude-code-skill. Run the official installer with the matching --agent value, read the generated INSTALLATION.md, verify the recorded absolute executable, and report the installed paths and revision.
```

After installation, start a new Codex or Claude Code session if the current session loaded its skill list before installation. In Codex, invoke `$xfetch`; in Claude Code, invoke `/xfetch`. Natural-language requests such as “save this URL locally: https://example.com/” also select the skill when automatic discovery is enabled.

For a local request, the skill uses `ingest` and writes to the first available location in this order: a destination explicitly requested by the user, `XFETCH_CONTENT_ROOT`, or `~/xfetch-content`. The skill passes that location explicitly, so direct CLI callers keep their existing `content-out` default. Local ingest does not publish, even when publication variables are present in the environment. Use `save` only when publication is intended and a target repository, owner, and name have been configured.

The installed skill's default local operation is equivalent to:

```bash
"<absolute xfetch executable from INSTALLATION.md>" ingest "https://example.com/" \
  --content-root "$HOME/xfetch-content" \
  --json
```

Each local capture is a bundle containing `document.json`, `index.md`, `publish.json`, and `assets/`. A successful publication adds `publication.json`. `document.json` records whether the capture is `complete`, `partial`, or `metadata_only`; the agent should report that status and any recorded limitation instead of presenting a partial capture as complete. A command failure exits non-zero and is not a successful capture.

Unicode characters in URL paths and queries are encoded before fetching. When a Medium author article URL (`medium.com/@author/title-<post-id>`) returns HTTP 403, xfetch tries the author's public RSS feed and selects the exact post ID. RSS `content:encoded` bodies and their image assets are captured. This fallback is `partial`: the feed body cannot be checked against the blocked article page. If the requested post is absent from the feed, capture fails instead of saving the latest unrelated entry. Title-only feeds are `metadata_only`.

If installation stops because an existing destination is modified or conflicts with the requested revision, preserve that installation, inspect the skill's `INSTALLATION.md` or the runtime's `.xfetch-runtime`, and resolve the conflict before retrying. To remove an installation, first verify each skill path against its `INSTALLATION.md`, the runtime against `.xfetch-runtime`, and every path against the installer-managed marker (`.xfetch-managed` containing `xfetch-installer-managed-v1`). Confirm that the copies contain no user files, then remove only the verified runtime and skill paths:

```bash
rm -rf -- "$HOME/.local/share/xfetch"
rm -rf -- "$HOME/.agents/skills/xfetch"
rm -rf -- "$HOME/.claude/skills/xfetch"
```

This does not remove captures under `~/xfetch-content` or shared `uv`/Python resources. Do not remove either of those locations as part of xfetch uninstall. Re-run the same installer command to repair a missing skill. If the managed runtime executable or `.xfetch-runtime` is missing or modified, inspect and remove the verified runtime first; the installer will preserve an incomplete runtime rather than rebuild it automatically.

## Goal

```text
caller / Hermes
      ↓
    xfetch
fetch → normalize → bundle
                    ↓
               publisher
                    ↓
           content repository
                    ↓
              static hosting
```

The runtime repository owns fetching, normalization, bundle creation, and publication mechanics. The target repository owns rendering, durable published artifacts, and any higher-level index/search experience.

## Capture contract

Every item is normalized into `NormalizedDocument` and written as:

```text
content-out/YYYY-MM/<slug>/
  document.json
  index.md
  publish.json
  assets/
  publication.json   # added after a successful publish
```

`document.json` includes explicit capture quality:

- `complete` — meaningful source content captured to the connector's supported contract.
- `partial` — useful content captured, but completeness is not guaranteed.
- `metadata_only` — only metadata/description/thumbnail captured.
- `failed` — reserved for explicit failed-capture records; normal CLI failures exit non-zero.

`content_kinds` describes captured material such as `text`, `images`, `transcript`, `metadata`, and `thumbnail`.

Every newly written bundle also includes a presentation-safe `card` object in `document.json`. `title` and `opening` are always present. When a suitable captured image exists, `image` points to its bundle-local path under `assets/`; otherwise the card remains text-only unless the caller supplies an optional visual generator. Source images are preferred over generated visuals, and invalid, tiny, logo/avatar, tracking, missing, or path-traversing candidates are not selected.

`index.md` is normalized as a detail-page document: its first blocks are the card title as an H1 and the card opening, followed by source details and the preserved captured body. Card enrichment is failure-isolated from capture and publication. A generator error is recorded under `metadata.card_enrichment`, while the bundle is still written with a text card and its original capture status.

Python callers that already have an image provider can pass a `VisualGenerator` to `write_bundle`. The provider receives a `VisualRequest` only when no suitable source visual exists. Diagram requests are limited to content with a process, hierarchy, architecture, comparison, or multi-component structure; other requests are text-free covers. There is no required provider dependency and the CLI does not make unconditional model calls.

Asset download failures are not silently ignored: the affected asset records a `capture_error`, `asset_capture_failures` is added to metadata, and a `complete` document is downgraded to `partial`.

## Supported source families

| Source | Current capture level |
|---|---|
| X status | `complete` for preserved text/photos through FxTwitter; posts with unpreserved video and oEmbed fallback are `partial` |
| Generic web | `partial` main/article-oriented text extraction |
| RSS / Atom | `complete` when a full content element is present, otherwise `partial` |
| Public Telegram | `partial` OpenGraph post representation |
| WeChat | article text/images when public HTML is available; verification pages fail explicitly |
| Xiaohongshu | image notes can be `complete`; video notes are `partial` until video preservation exists; login walls fail explicitly |
| YouTube | `partial` when public captions can be captured; otherwise `metadata_only` |
| Feishu / Lark wiki and docx | document text when the page is anonymously readable; images, files, and sheets are not preserved; `partial` when those blocks are present, otherwise `complete` for the text capture |
| Bilibili | `partial` when public subtitles can be captured, otherwise `metadata_only`; `/opus/<id>` posts capture article text and images from the public opus API (`partial` when a paragraph type is skipped) |

YouTube caption capture is best-effort. Some caption tracks are advertised by YouTube but require additional playback tokens; those remain `metadata_only` and record the transcript capture failure instead of failing the whole save. Video bytes are not preserved, so transcript-backed YouTube bundles remain `partial`.

Bilibili subtitle capture uses the public player subtitle list. Videos with public subtitle tracks are captured as `partial`; subtitles that require login remain `metadata_only` with that limitation recorded. Video bytes are not preserved.

Feishu and Lark (`feishu.cn`, `larksuite.com`, `larkoffice.com`) wiki and docx URLs are read with the anonymous session cookies the redirect sets, then the docx `client_vars` payload. Permission failures raise an error and do not save the login shell.

Bilibili opus URLs (`/opus/<numeric id>`) use the public opus detail API. `/video/` URLs still require a BV id.

Zhihu column pages that return the zse-ck anti-bot challenge fail with an explicit error. Changing the User-Agent does not capture the article, and xfetch does not save the challenge page.

## Network safety

xfetch accepts public HTTP(S) sources only. Before a request, after a redirect, and before downloading an asset, it resolves the destination and rejects non-public addresses (loopback, private, link-local, reserved, metadata endpoints, and similar ranges). Responses are size-limited to reduce accidental unbounded downloads.

This is a security boundary because xfetch is intended to sit behind an agent/chat front door.

## CLI

For repository development, install the editable package separately from the user skill installer:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/xfetch --help
```

### Save

`save` is the canonical one-shot command:

```bash
python -m xfetch save "https://x.com/jack/status/20" --json
```

With publication defaults:

```bash
export XFETCH_TARGET_REPO='/path/to/content-repo'
export XFETCH_REPO_OWNER='owner'
export XFETCH_REPO_NAME='content-repo'

python -m xfetch save "https://example.com/" \
  --content-root ./content-out \
  --json
```

Publication is optional. It requires an existing target checkout and the matching repository settings; hosting and deployment remain responsibilities of that target repository.

Optional environment overrides:

- `XFETCH_BRANCH`
- `XFETCH_CONTENT_SUBDIR`
- `XFETCH_CONTENT_ROOT`

JSON output includes capture quality plus publication state:

```json
{
  "ok": true,
  "source_type": "web",
  "capture_status": "partial",
  "content_kinds": ["text", "metadata"],
  "bundle_dir": "...",
  "published": true,
  "public_url": "...",
  "revision": "<publish commit>",
  "receipt_revision": "<publish commit>"
}
```

### Ingest

```bash
python -m xfetch ingest "https://example.com/" --json
```

Writes a local bundle without publishing it.

### Sync

```bash
python -m xfetch sync ./content-out/2026-08/web-example \
  --target-repo /path/to/target \
  --repo-owner owner \
  --repo-name repo
```

Copies the bundle into a target working tree without committing.

### Publish

```bash
python -m xfetch publish ./content-out/2026-08/web-example \
  --target-repo /path/to/target \
  --repo-owner owner \
  --repo-name repo
```

Publication stages only the generated bundle path. Unrelated dirty files are left untouched, and unrelated pre-staged changes cause publication to fail instead of being swept into a publish commit.

The publisher writes final `publish.json` and `publication.json` into the target bundle (with `revision` / `content_revision` left null in git), creates one `publish: <slug>` commit, and pushes once. After push, it updates the local source bundle and target working tree with the returned commit SHA without committing again, so the revision is not self-referential inside the published tree. JSON output still includes `receipt_revision` for compatibility; it matches `revision`.

For an existing remote branch, the target checkout must start exactly at `origin/<branch>` before publication. This prevents unrelated local commits from being swept into the publish push.

## Rendering

xfetch keeps a small dependency-free renderer for local preview/export. It handles headings, paragraphs, fenced code, images, ordered/unordered lists, blockquotes, links, inline code, and bold text. Publication does not copy rendered pages into the target repository; the normalized bundle remains the durable source of truth and the target owns presentation.

## Development

```bash
pytest -q
```

Pull requests run the test suite on Python 3.10, 3.11, and 3.12.
