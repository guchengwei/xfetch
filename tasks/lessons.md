# Lessons

## 2026-02-23 — End-to-end verification gap

**Mistake:** Plan verification tested the fetcher layer directly (`fetch_twitter()` → raw dict).
Two bugs survived into commit:
1. `from_twitter()` not pulling `data["quote"]["transcript"]` (only checked outer tweet)
2. `UniversalReader` using relative `./unified_inbox.json` instead of `INBOX_FILE` env var

**Rule:** For any plan touching fetcher + schema + storage, verification MUST trace the
full pipeline end-to-end:
```
reader.read(url) → UnifiedContent fields → file written to INBOX_FILE
```
Specifically check:
- `uc.extra['has_transcript']` is True (not just that the fetcher returned a transcript)
- `INBOX_FILE` on disk contains the new entry
- Content length is plausible (includes enrichment, not just tweet text)

**Never** accept a test that stops at the fetcher's raw dict output when the plan
also touches schema conversion or storage.
