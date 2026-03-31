# X Fetcher Executor Brief

Primary plan:
- `docs/plans/2026-03-31-x-fetcher-content-pipeline-plan.md`

Use x-tweet-fetcher as the implementation base.
Do not treat link-vault as the primary codebase.
Treat link-vault as an optional content/publish target repo.

## Key product split
Runtime:
- x-tweet-fetcher
- fetch, normalize, ASR, bundle, search, publish/sync

Target repo:
- link-vault or another content repo
- stores generated content/site artifacts
- may host GitHub Pages

## Hard requirements
1. Stable public links via publishing, ideally GitHub Pages on target repo
2. Portable runtime with no hidden path assumptions
3. Local-first transcription via faster-whisper
4. No dependence on one shared mutable DB across environments

## First things to build
1. `xfetch/` package scaffold
2. config/models/db modules
3. backend modules from current scripts
4. normalized document model
5. portable content bundles
6. target repo sync abstraction

## Important principle
The durable cross-env interface is the content bundle, not the local SQLite DB.

## Recommended first milestone
- migrate X connector
- migrate one non-X connector
- write bundle output locally
- sync bundle to target repo working tree
