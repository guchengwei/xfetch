# Changelog

## 0.2.4 - 2026-10-07

- capture X Article title, body, and images when FxTwitter and VxTwitter are blocked and oEmbed is only a short t.co card, using X's public guest post lookup (no user token)
- try FxTwitter, then VxTwitter, before that guest lookup; optional `XFETCH_X_BEARER_TOKEN` calls the official posts API only if those fail
- keep an article cover image in the captured markdown, and skip a preview card that only repeats the opening of the body

## 0.2.3 - 2026-10-06

- publish target bundles in a single `publish: <slug>` commit that includes final `publish.json` and `publication.json`, with one push to the target repo
- record the publish commit SHA in local and working-tree metadata after push so git trees do not embed self-referential revisions

## 0.2.2 - 2026-10-05

- preserve headings, paragraphs, lists, and inline images in captured markdown via the shared `article_html` converter (WeChat, generic web articles, X posts and articles, Xiaohongshu notes)
- capture anonymously readable Feishu and Lark wiki/docx pages (cookies across redirects; wiki `SERVER_DATA` and docx `client_vars`); skip images, files, and sheets with `partial` captures
- capture Bilibili `/opus/<id>` article text and images through the public polymer opus API
- fail Zhihu `zse-ck` HTTP 403 challenges with an explicit error and write no bundle

## 0.2.1 - 2026-10-03

- allow egress proxy fake-ip range `198.18.0.0/15` in `validate_public_url` while still refusing localhost, real private, link-local, and metadata addresses

## 0.2.0 - 2026-08-29

- add public-network validation for source fetches, redirects, and asset downloads
- add bounded response reads for fetch operations
- add `capture_status` and `content_kinds` to the normalized document contract
- downgrade captures when durable asset materialization fails instead of silently claiming completeness
- reject WeChat verification pages and Xiaohongshu login walls as source content
- add a validated X oEmbed fallback when FxTwitter is unavailable and preserve normal X photos
- capture public YouTube captions and Bilibili subtitles as `partial` content while keeping unavailable/inaccessible transcripts `metadata_only`
- resolve Bilibili short links and preserve YouTube Shorts/live video identity
- replace bundles atomically so stale assets and publication receipts cannot survive re-ingest
- scope git publication to generated bundle paths, reject unrelated staged/committed work, and require a clean remote base
- split content revision from publication receipt metadata and push both commits together
- publish content bundles only; target repositories own rendering and presentation
- keep the dependency-free renderer for local preview/export
- replace the legacy agent skill description with the active xfetch interface
- remove the runtime repo's obsolete Pages deployment workflow and add pytest CI

## 0.1.0 - 2026-04

- establish xfetch as the canonical save/publish runtime
- introduce normalized portable bundles and the connector registry
- add X, web, RSS, Telegram, WeChat, Xiaohongshu, YouTube, and Bilibili connectors
- add separate target-repository sync/publish support and static page rendering

Earlier x-reader / x-tweet-fetcher history remains available in git history and archived planning documents; it is not the active xfetch product contract.
