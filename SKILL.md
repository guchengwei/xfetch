---
name: xfetch
description: >
  Preserve a supported public URL as a portable local bundle and optionally publish it
  into a separate content repository. Use for save/archive/preserve-link requests.
---

# xfetch

Use xfetch when the user wants to save or preserve the content behind a URL. xfetch is not a search tool, timeline reader, bookmark manager, or general-purpose browser.

## Installed runtime

When this skill is installed by the supported installer, `INSTALLATION.md` is beside this file. Read it before running xfetch. Use the absolute executable path recorded there for every invocation; do not depend on the current directory, an activated virtual environment, or `PATH`. The reference also records the default local archive location and installed revision.

If `INSTALLATION.md` is missing or unreadable, stop and direct the user to the README installation section for the intended host (`codex`, `claude`, or `both`), then re-read the generated reference. Do not guess a Python module, activate an environment, or fall back to `PATH`.

## Canonical command

```bash
"<absolute xfetch executable>" ingest "<url>" \
  --content-root "<explicit destination or XFETCH_CONTENT_ROOT or the INSTALLATION.md default>" \
  --json
```

For a normal preservation request, use `ingest` so inherited publication variables cannot publish unexpectedly. Choose the content root in this order: a destination explicitly requested by the user, `XFETCH_CONTENT_ROOT`, then the default recorded in `INSTALLATION.md` (normally `~/xfetch-content`). Pass the selected path explicitly. The direct CLI default remains `content-out` outside the installed skill.

## Publication command

Use `save` when the user intends publication and the target repository settings are configured:

```bash
"<absolute xfetch executable>" save "<url>" --json
```

When publish defaults are configured, `save` performs ingest, bundle creation, and publication, then returns the public URL. Without publish configuration it returns the local bundle path.

Publish defaults:

```bash
export XFETCH_TARGET_REPO='/path/to/content-repo'
export XFETCH_REPO_OWNER='owner'
export XFETCH_REPO_NAME='repo'
```

Optional overrides: `XFETCH_BRANCH`, `XFETCH_CONTENT_SUBDIR`, `XFETCH_CONTENT_ROOT`.

## Local versus publication requests

Publication requires `XFETCH_TARGET_REPO`, `XFETCH_REPO_OWNER`, and `XFETCH_REPO_NAME` (with optional branch and subdirectory overrides); report the returned `public_url` and revisions only when the command reports success. Do not configure or publish to a target merely because one exists in the environment.

## Other commands

```bash
"<absolute xfetch executable>" ingest "<url>" --content-root "<root>" --json
"<absolute xfetch executable>" sync <bundle-dir> --target-repo <repo> --repo-owner <owner> --repo-name <name> --json
"<absolute xfetch executable>" publish <bundle-dir> --target-repo <repo> --repo-owner <owner> --repo-name <name> --json
```

Use `sync` to prepare a target working tree without committing. Use `publish` for an existing bundle when publication is explicitly requested. Publication copies durable bundle content only; the target repository owns rendering and presentation.

## Result semantics

A normalized document includes `capture_status`:

- `complete`: connector captured the meaningful source content it knows how to preserve.
- `partial`: usable content was captured, but completeness is not guaranteed.
- `metadata_only`: only metadata/description/thumbnail was captured; do not describe this as full preservation.
- `failed`: reserved for explicit failed-capture records; normal CLI failures return non-zero instead.

`content_kinds` describes what was captured, such as `text`, `images`, `transcript`, `metadata`, or `thumbnail`.

When `save --json` reports `published: true`, return its `public_url` as the saved link. Also preserve the reported `capture_status`; do not describe a `partial` or `metadata_only` result as a complete archive.

After publication, `publication.json` records the content commit revision and public URL. The target repository is a content/output surface; xfetch remains the ingestion runtime.

## Supported source families

- X status URLs
- generic public web pages
- RSS/Atom feeds
- public Telegram URLs
- WeChat articles
- Xiaohongshu notes when public HTML contains the note state
- YouTube video URLs: `partial` when public captions are captured, otherwise `metadata_only`
- Bilibili video URLs: `partial` when public subtitles are captured, otherwise `metadata_only`
- Bilibili `/opus/<id>` posts: article text and images from the public opus API (`partial` when a paragraph type is skipped)
- Feishu / Lark wiki and docx URLs when anonymously readable: document text (`partial` when image, file, or sheet blocks are present; otherwise `complete` for text)
- Zhihu column pages: zse-ck anti-bot challenges are not captured

YouTube caption tracks can be advertised but inaccessible without additional playback tokens; keep those results `metadata_only` and report the recorded capture limitation. Bilibili subtitles that require login likewise remain `metadata_only`.

If WeChat returns a verification page, Feishu or Lark returns a permission error, or Xiaohongshu returns a login wall, report the fetch failure rather than saving the interstitial as content. A Zhihu zse-ck HTTP 403 is a failed capture: report the error and do not claim the URL was saved.

## Capture results

Keep the reported `capture_status` and `content_kinds` in the response. A `partial` or `metadata_only` result is still a useful output when the bundle exists, but must be described with its limitation. If the CLI exits non-zero, report the failure and do not claim that the URL was saved.

## Safety

Only public HTTP(S) destinations are fetchable. xfetch rejects loopback, private, link-local, reserved, and metadata-network destinations, including redirects and downloaded assets.
