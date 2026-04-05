# xfetch Replace x-reader Implementation Plan

> For Hermes: use subagent-driven-development to execute this plan task-by-task.

Goal: make xfetch the only operational save/publish pipeline and migrate the highest-value x-reader fetch capabilities into xfetch until x-reader can be safely retired.

Architecture: keep xfetch as the single runtime spine (ingest -> bundle -> sync/publish -> public URL), then port source-specific readers into xfetch as connectors/adapters behind a single connector registry. Do not drag x-reader’s inbox-centric storage model forward; only preserve source-fetching capability that still matters.

Tech stack: Python, argparse CLI, xfetch bundle/publish pipeline, existing x-reader fetcher code as migration source, pytest.

---

## Current state snapshot

Confirmed from the codebase today:
- xfetch package scope is still narrow: single X URL -> bundle -> sync/publish (`x-tweet-fetcher/README.md`, `xfetch/cli.py`).
- xfetch runtime currently only picks `XConnector` (`xfetch/cli.py`).
- x-reader still has broader routing support in `x_reader/reader.py` for:
  - X/Twitter
  - WeChat
  - Xiaohongshu
  - YouTube
  - Bilibili
  - RSS
  - Telegram
  - generic web fallback
- Therefore the right path is not “delete x-reader now”; it is “freeze x-reader operationally, migrate source support into xfetch, then retire x-reader”.

## Target end state

One user-facing path only:
- Hermes request -> xfetch ingest -> bundle write -> publish to `/Users/zion/link-vault-publish` -> GitHub Pages URL

One runtime package only:
- xfetch owns all actively used connectors
- x-reader becomes archived reference code or is deleted after parity is good enough

## Migration principles

1. xfetch stays the only publish/runtime spine.
2. Migrate source fetchers one connector at a time.
3. Keep TDD for every connector port.
4. Do not copy x-reader’s inbox model into xfetch.
5. Freeze x-reader as non-operational as soon as Hermes routing is locked.
6. Only migrate sources you still care about.

## Recommended source priority

Priority 0: X/Twitter
- already in xfetch; make it the only Hermes save path

Priority 1: WeChat, Xiaohongshu, RSS, generic web fallback
- highest practical value for link archiving
- mostly article/post style content that fits xfetch bundles cleanly

Priority 2: Bilibili, YouTube
- migrate only the text/subtitle/article extraction path first
- defer full transcript/AI analysis extras unless still needed

Priority 3: Telegram channel fetch
- migrate only if you still actively save Telegram links/channels through this stack

Defer / maybe never migrate:
- x-reader-specific inbox/list/clear UX
- analysis/report skills tightly coupled to x-reader naming
- anything that does not serve the “save a link into portable published bundles” job

---

## Phase 1: Lock operations to xfetch only

### Task 1: Audit current Hermes save routing
Objective: identify every place Hermes can still hit x-reader for save-style requests.

Files:
- Inspect: Hermes routing/config in the active environment
- Inspect: any local wrappers/scripts invoking `x-reader`
- Inspect: docs and prompts that describe the active save path

Steps:
1. Search for `x-reader`, `save this`, `/save`, `/link`, `xfetch`, `xfetch telegram-bot` across the local setup.
2. Record every operational path that still references x-reader.
3. Categorize each as: keep, replace with xfetch, or delete.

Verification:
- There is a written list of all operational entrypoints.

### Task 2: Make Hermes save routing explicitly xfetch-only
Objective: remove ambiguity so “save this <url>” cannot go to x-reader again.

Files:
- Modify the active Hermes routing/integration layer once identified in Task 1
- Update any local wrapper scripts if they still call `x-reader`

Steps:
1. Change the default save action to call xfetch only.
2. Remove or disable x-reader fallback for save/publish requests.
3. Keep x-reader callable manually only if needed for temporary reference use.

Verification:
- A test/manual run for an X URL goes through xfetch and returns publish output, not local inbox output.

### Task 3: Mark x-reader as frozen for operations
Objective: prevent future confusion while migration is in progress.

Files:
- `projects/x-reader/README.md`
- any local docs/notes that present x-reader as active save runtime

Steps:
1. Add a prominent note: x-reader is legacy/reference for source logic; operational save/publish is xfetch.
2. Remove examples that imply x-reader is the active publishing route.

Verification:
- Docs no longer present x-reader as the main save pipeline.

---

## Phase 2: Build connector infrastructure in xfetch

### Task 4: Introduce a connector registry in xfetch
Objective: stop hardcoding `XConnector()` in `pick_connector()`.

Files:
- Modify: `xfetch/cli.py`
- Create: `xfetch/connectors/registry.py`
- Test: `tests/test_connector_registry.py`

Implementation shape:
- `registry.py` exports ordered connector instances or factories
- `pick_connector(url)` iterates registry and returns the first connector whose `can_handle(url)` is true

Tests:
- picks X connector for X URL
- returns None for unsupported URL
- later tests can expand as connectors are added

Verification:
- `pytest tests/test_connector_registry.py -v`

### Task 5: Define migration adapter contract
Objective: make ports from x-reader consistent.

Files:
- Modify/create: `xfetch/connectors/base.py`
- Create: `tests/test_connector_contract.py`
- Optionally create: `xfetch/connectors/adapters.py`

Contract expectations:
- `can_handle(url: str) -> bool`
- `fetch(url: str) -> NormalizedDocument`
- no inbox writes
- no markdown side effects
- all outputs normalized into xfetch bundle schema

Verification:
- contract test passes for XConnector and future connectors

---

## Phase 3: Port highest-value non-X sources

### Task 6: Port generic web fallback first
Objective: give xfetch a universal baseline before source-specific ports.

Files:
- Create: `xfetch/connectors/web.py`
- Create/update tests: `tests/test_web_connector.py`

Behavior:
- handles generic http/https URLs not claimed by a more specific connector
- uses the simplest stable fetch path available
- outputs NormalizedDocument suitable for bundle write/publish

Why first:
- immediately reduces dependency on x-reader for many links
- lowers urgency of migrating every source-specific connector at once

Verification:
- generic article URL ingests through xfetch and writes a valid bundle

### Task 7: Port RSS connector
Objective: support feed URLs in xfetch.

Files:
- Create: `xfetch/connectors/rss.py`
- Create: `tests/test_rss_connector.py`

Scope:
- single feed URL -> first/latest entry normalized into one document
- no inbox behavior

Verification:
- RSS fixture test passes

### Task 8: Port WeChat connector
Objective: migrate one of the highest-value article sources.

Files:
- Create: `xfetch/connectors/wechat.py`
- Create: `tests/test_wechat_connector.py`
- Reuse logic from x-reader fetcher only as needed

Scope:
- preserve existing stable extraction paths
- normalize to xfetch document schema
- no x-reader schema leakage

Verification:
- WeChat fixture/manual URL ingests through xfetch

### Task 9: Port Xiaohongshu connector
Objective: migrate another high-value source used for saving posts.

Files:
- Create: `xfetch/connectors/xiaohongshu.py`
- Create: `tests/test_xiaohongshu_connector.py`

Scope:
- post/note extraction only
- normalize text/media metadata into xfetch bundles

Verification:
- fixture/manual URL ingests through xfetch

### Task 10: Wire new connectors into registry
Objective: make the newly ported connectors discoverable in the real CLI.

Files:
- Modify: `xfetch/connectors/registry.py`
- Modify tests as needed

Verification:
- `python -m xfetch ingest <url>` chooses the expected connector for web/RSS/WeChat/Xiaohongshu URLs

---

## Phase 4: Add media connectors only if needed

### Task 11: Port YouTube text/subtitle path
Objective: support basic save flow for YouTube without overbuilding analysis features.

Files:
- Create: `xfetch/connectors/youtube.py`
- Create: `tests/test_youtube_connector.py`

Scope:
- title/metadata/description/subtitles when available
- no separate AI analysis layer

Verification:
- URL ingests into a valid xfetch bundle

### Task 12: Port Bilibili text/subtitle path
Objective: support Bilibili in the same minimal style.

Files:
- Create: `xfetch/connectors/bilibili.py`
- Create: `tests/test_bilibili_connector.py`

Verification:
- URL ingests into a valid xfetch bundle

### Task 13: Decide on Telegram channel support
Objective: explicitly decide whether Telegram fetch belongs in xfetch.

Decision rule:
- migrate only if you actually use Telegram link/channel saves in the archive workflow
- otherwise mark as intentionally not migrated

Output:
- one explicit decision recorded in docs

---

## Phase 5: Decommission x-reader safely

### Task 14: Remove x-reader from all operational docs and scripts
Objective: ensure no active workflow points at it.

Files:
- update local docs/scripts found in Phase 1
- update any setup instructions that still mention x-reader as active save runtime

Verification:
- searching operational configs/scripts for `x-reader` returns reference-only mentions

### Task 15: Add an xfetch migration status section to README
Objective: show what is migrated and what is intentionally unsupported.

Files:
- Modify: `x-tweet-fetcher/README.md`

Suggested section:
- migrated: X, generic web, RSS, WeChat, Xiaohongshu, etc.
- planned: YouTube/Bilibili/Telegram if applicable
- deprecated: x-reader operational pipeline

Verification:
- README clearly states xfetch is the canonical runtime

### Task 16: Archive or delete x-reader
Objective: finish the consolidation once parity is sufficient.

Decision gate before doing this:
- all sources you still care about are usable in xfetch
- Hermes save flow has been xfetch-only for a while without regressions
- no active scripts/services rely on x-reader

Possible actions:
- archive repo and keep as reference
- or delete if truly unnecessary

---

## Immediate recommendation

Do these first, in order:
1. Lock Hermes save routing to xfetch only.
2. Freeze x-reader operationally in docs.
3. Add xfetch connector registry.
4. Port generic web fallback.
5. Port RSS.
6. Port WeChat.
7. Port Xiaohongshu.

That gives the biggest clarity win fastest.

## What not to do

- Do not try to port every x-reader feature before locking routing.
- Do not move x-reader inbox/list/clear concepts into xfetch.
- Do not keep both pipelines active while connector migration is happening.
- Do not claim xfetch replaces x-reader until the actually used sources are migrated.

## Verification checklist

- “save this <x-url>” only uses xfetch
- xfetch publish still works to `/Users/zion/link-vault-publish`
- x-reader is documented as legacy/reference only
- xfetch supports the migrated non-X sources with tests
- no operational scripts/services still depend on x-reader

## Execution suggestion

Use this as the implementation order:
- Milestone A: routing lock + docs freeze
- Milestone B: connector registry + generic web + RSS
- Milestone C: WeChat + Xiaohongshu
- Milestone D: media/Telegram only if still needed
- Milestone E: x-reader retirement
