# Operational routing

Canonical save/publish path on this machine:
- Hermes natural-language request (for example: `save this <url>`)
- xfetch runtime
- target working tree: `/Users/zion/link-vault-publish`
- target repo/site: `guchengwei/link-vault`

Rules:
- Do not satisfy save/publish requests with x-reader.
- Treat x-reader as legacy/reference tooling while connector migration is in progress.
- Use xfetch as the only operational save/publish pipeline.

Audit notes (2026-04-03):
- xfetch package runtime is the canonical publish spine.
- x-reader still exists as a broader reader, but it is no longer the active save/publish path.
- New connector migration work in xfetch currently covers: X, RSS, generic web.
