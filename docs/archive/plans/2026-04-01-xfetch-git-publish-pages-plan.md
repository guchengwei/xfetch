# X Fetcher Git Publish + Pages Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add a real publish workflow on top of local bundle sync so `xfetch` can sync a bundle into a target repo, render a publish-ready static page, commit and push the target repo, and record the resulting GitHub Pages URL and pushed revision.

**Architecture:** Keep ingestion local and lightweight in the runtime. Publishing is a second phase: render a static page from an existing bundle, sync bundle plus rendered page into a target repo working tree, then commit/push that target repo and record `public_url` and `revision` in `publish.json`. GitHub Actions in the target repo handles the final Pages deployment from already-rendered site artifacts.

**Tech Stack:** Python 3.10+, stdlib, pytest, git CLI, GitHub Actions Pages deploy, local filesystem bundles and target repo working trees.

---

## Scope of this milestone

This milestone includes:
- publish config for repo owner/name/branch and site subdir
- static page rendering for one bundle
- sync of both bundle artifacts and rendered site artifacts into a target repo
- git add/commit/push helper for the target repo
- public URL computation for GitHub Pages
- `publish.json` updates with target repo metadata, revision, and `public_url`
- CLI `publish` command
- GitHub Actions workflow to deploy `site/` on pushes to `main`
- tests for rendering, git publish metadata, and CLI publish behavior

This milestone does not include:
- multi-bundle site indexes, feeds, or search pages
- PR-based publish workflow
- automatic Pages deployment polling/status checks
- non-GitHub hosting targets
- ASR/media expansion

---

## Non-negotiable decisions

1. Runtime still performs ingest/render locally; GitHub Actions does not run scraping/transcription.
2. Target repo remains the publication surface.
3. Rendered site artifacts are pushed into the target repo under `site/`.
4. Bundles remain source-of-truth artifacts under `content/`.
5. GitHub Actions only deploys the pushed `site/` directory.
6. `public_url` is computed deterministically from repo owner/name and bundle slug.
7. Publishing must be idempotent for the same bundle path.
8. This milestone supports GitHub project pages URLs only: `https://<owner>.github.io/<repo>/...`.

Development note:
- run tests from the repo root
- editable install is only required during final verification, not before Task 1

---

## Publish contract for this milestone

A successful publish does all of the following:
- copies bundle artifacts into `content/YYYY-MM/<slug>/`
- renders a static page into `site/d/<slug>/index.html`
- writes the same rendered page into the target repo
- commits changed files in the target repo
- pushes the target repo branch
- updates source bundle `publish.json`
- updates target bundle copy `publish.json`

`publish.json` after a successful publish must look like:

```json
{
  "published": true,
  "public_url": "https://<owner>.github.io/<repo>/d/<slug>/",
  "target": {
    "type": "github_pages",
    "repo_owner": "<owner>",
    "repo_name": "<repo>",
    "branch": "main",
    "bundle_path": "content/YYYY-MM/<slug>",
    "site_path": "site/d/<slug>/index.html"
  },
  "revision": "<git-sha>"
}
```

---

## GitHub Pages workflow contract

Create `.github/workflows/deploy-pages.yml` in the target repo.

Behavior:
- trigger on pushes to `main` touching `site/**` or manually via workflow_dispatch
- use `actions/configure-pages`, `actions/upload-pages-artifact`, `actions/deploy-pages`
- grant `pages: write` and `id-token: write` permissions
- upload `site/` as the Pages artifact
- do not build or mutate content in the workflow

This keeps deployment a pure last-mile step.

---

## Locked file plan for this milestone

### Create
- `.github/workflows/deploy-pages.yml`
- `xfetch/publishing/url.py`
- `xfetch/publishing/git_publish.py`
- `xfetch/storage/__init__.py`
- `xfetch/storage/render.py`
- `tests/test_render.py`
- `tests/test_git_publish.py`

### Modify
- `xfetch/config.py`
- `xfetch/publishing/base.py`
- `xfetch/publishing/github_repo_sync.py`
- `xfetch/cli.py`
- `tests/test_cli.py`
- `tests/test_publishing.py`
- `README.md`

---

## Runtime config contract additions

Extend `RuntimeConfig` with:

```python
publish_branch: str = "main"
site_subdir: str = "site"
```

Add a new dataclass:

```python
@dataclass(slots=True)
class PublishTargetConfig:
    repo_owner: str
    repo_name: str
    branch: str = "main"
    content_subdir: str = "content"
    site_subdir: str = "site"
```

Do not make these required for ingest-only commands.

---

## Static render contract

Render one bundle page to:

```text
site/d/<slug>/index.html
```

HTML requirements for this milestone:
- include `<title>` from document title
- include canonical link to computed public URL when provided
- include source URL, author handle, created_at, text body
- preserve simple line breaks in text
- no JS build pipeline
- plain static HTML only

Do not try to build site indexes in this milestone.

---

## CLI contract additions

Add:

```bash
python -m xfetch publish <bundle_dir> \
  --target-repo ../target-repo \
  --repo-owner guchengwei \
  --repo-name x-reader
```

Optional flags:

```bash
--branch main
--content-subdir content
--site-subdir site
--json
```

Behavior:
1. validate bundle
2. render static page for bundle
3. sync bundle + rendered page into target repo
4. git add/commit/push target repo
5. compute `public_url`
6. write updated `publish.json`
7. print JSON summary or destination path

Unsupported/missing git repo should return non-zero.

---

## Testing rules

1. No network in tests.
2. No real remote pushes in tests.
3. Git tests must use temporary local repos only.
4. Verify both source and target `publish.json` payloads.
5. Verify rendered HTML contains title and canonical URL.
6. Verify CLI publish path with a real local git repo and no monkeypatching when practical.
7. Configure git identity explicitly inside temporary test repos before asserting commit/push behavior.
8. Verify commit is skipped when there are no content changes only if the implementation supports that; otherwise keep one deterministic commit path for this milestone.

---

## Task 1: Add publish URL helpers and config extensions

**Objective:** Lock public URL computation and publish target config before implementing render/push.

**Files:**
- Create: `xfetch/publishing/url.py`
- Modify: `xfetch/config.py`
- Test: `tests/test_git_publish.py`

**Step 1: Write failing tests**

```python
from xfetch.config import PublishTargetConfig
from xfetch.publishing.url import build_pages_url


def test_build_pages_url_for_project_pages_repo():
    cfg = PublishTargetConfig(repo_owner="guchengwei", repo_name="x-reader")
    url = build_pages_url(cfg, slug="x-123-alice")
    assert url == "https://guchengwei.github.io/x-reader/d/x-123-alice/"
```

**Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_git_publish.py -q`
Expected: FAIL with missing module/import

**Step 3: Implement minimal code**

`xfetch/publishing/url.py` must expose:
- `build_pages_url(config: PublishTargetConfig, slug: str) -> str`

Extend `xfetch/config.py` with `PublishTargetConfig`.

**Step 4: Run test to verify pass**

Run: `python -m pytest tests/test_git_publish.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add xfetch/config.py xfetch/publishing/url.py tests/test_git_publish.py
git commit -m "feat: add publish target config and pages url helpers"
```

---

## Task 2: Add static page renderer

**Objective:** Render a single bundle into a publish-ready static page.

**Files:**
- Create: `xfetch/storage/__init__.py`
- Create: `xfetch/storage/render.py`
- Test: `tests/test_render.py`

**Step 1: Write failing tests**

```python
from pathlib import Path
from xfetch.storage.render import render_bundle_page


def test_render_bundle_page_writes_index_html(tmp_path):
    bundle_dir = tmp_path / "2026-03" / "x-123-alice"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "document.json").write_text(
        '{"title":"Hello","canonical_url":"https://x.com/alice/status/123","author_handle":"alice","created_at":"2026-03-31T00:00:00Z","text":"hello world"}',
        encoding="utf-8",
    )
    out_dir = tmp_path / "site"
    page = render_bundle_page(bundle_dir, out_dir, public_url="https://guchengwei.github.io/x-reader/d/x-123-alice/")
    assert page == out_dir / "d" / "x-123-alice" / "index.html"
    html = page.read_text(encoding="utf-8")
    assert "<title>Hello</title>" in html
    assert "rel=\"canonical\"" in html
```

**Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_render.py -q`
Expected: FAIL

**Step 3: Implement minimal code**

`xfetch/storage/render.py` must expose:
- `render_bundle_page(bundle_dir: Path, site_root: Path, public_url: str | None = None) -> Path`

Rules:
- read `document.json`
- write `site_root/d/<slug>/index.html`
- HTML-escape user content
- replace newlines in text with `<br>`

**Step 4: Run test to verify pass**

Run: `python -m pytest tests/test_render.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add xfetch/storage/__init__.py xfetch/storage/render.py tests/test_render.py
git commit -m "feat: add static bundle page renderer"
```

---

## Task 3: Extend repo sync to include site artifacts and publish metadata payload

**Objective:** Sync both bundle and rendered site page into the target repo with GitHub Pages metadata.

**Files:**
- Modify: `xfetch/publishing/base.py`
- Modify: `xfetch/publishing/github_repo_sync.py`
- Modify: `tests/test_publishing.py`

**Step 1: Write failing tests**

Add tests asserting:
- rendered page is copied into `site/d/<slug>/index.html`
- `publish.json` target type becomes `github_pages`
- target metadata includes `repo_owner`, `repo_name`, `branch`, `bundle_path`, `site_path`

**Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_publishing.py -q`
Expected: FAIL

**Step 3: Implement minimal code**

Update sync interface to accept:
- `rendered_page`
- `publish_target`

Return `PublishResult` with:
- `bundle_destination_dir`
- `site_destination_path`
- `target_path`

**Step 4: Run test to verify pass**

Run: `python -m pytest tests/test_publishing.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add xfetch/publishing/base.py xfetch/publishing/github_repo_sync.py tests/test_publishing.py
git commit -m "feat: sync rendered site artifacts with publish metadata"
```

---

## Task 4: Add git-backed publish helper

**Objective:** Commit and push the target repo and return the pushed revision.

**Files:**
- Create: `xfetch/publishing/git_publish.py`
- Test: `tests/test_git_publish.py`

**Step 1: Write failing tests**

Use temporary git repos to verify:
- helper commits changes in target repo
- helper returns a revision SHA
- helper can push to a local bare remote in tests

**Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_git_publish.py -q`
Expected: FAIL

**Step 3: Implement minimal code**

`xfetch/publishing/git_publish.py` must expose:
- `publish_repo(target_repo: Path, branch: str, commit_message: str) -> str`

Rules:
- verify `target_repo/.git` exists
- run `git add -A`
- commit with provided message
- push `branch`
- return `git rev-parse HEAD`

If there are no staged changes, allow a no-op commit path by returning current HEAD without failing.

**Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_git_publish.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add xfetch/publishing/git_publish.py tests/test_git_publish.py
git commit -m "feat: add git-backed target repo publisher"
```

---

## Task 5: Add CLI publish flow

**Objective:** Expose one end-to-end publish command.

**Files:**
- Modify: `xfetch/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Write failing tests**

Add tests for:
- `publish` parser shape
- local-git publish flow writes `public_url`
- CLI returns non-zero when target repo is not a git repo

**Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_cli.py -q`
Expected: FAIL

**Step 3: Implement minimal code**

Add `publish` subcommand and `run_publish(args)`.

Commit message format for this milestone:

```text
publish: <slug>
```

JSON output shape:

```json
{
  "ok": true,
  "bundle_dir": "...",
  "public_url": "https://...",
  "revision": "<sha>",
  "target_repo": "..."
}
```

**Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_cli.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add xfetch/cli.py tests/test_cli.py

git commit -m "feat: add publish command"
```

---

## Task 6: Add GitHub Pages workflow and docs

**Objective:** Add the deployment workflow and document the publish path.

**Files:**
- Create: `.github/workflows/deploy-pages.yml`
- Modify: `README.md`

**Step 1: Add workflow**

Use a Pages workflow that:
- triggers on pushes to `main` affecting `site/**`
- uploads `site/`
- deploys via GitHub Pages

**Step 2: Update README**

Add a short section showing:

```bash
python -m xfetch publish ./content-out/2006-03/x-20-jack \
  --target-repo ../target-repo \
  --repo-owner guchengwei \
  --repo-name x-reader
```

State clearly:
- publish assumes the target repo already has git remote/auth configured
- Pages deploy happens in GitHub Actions on push to `main`

**Step 3: Commit**

```bash
git add .github/workflows/deploy-pages.yml README.md
git commit -m "docs: add pages deployment workflow and publish usage"
```

---

## Final verification checklist

Run from repo root:

```bash
python -m pytest -q
python -m xfetch --help
```

Then run a local integration check with a temporary target git repo:

```bash
python -m xfetch ingest "https://x.com/jack/status/20"
python -m xfetch publish ./content-out/2006-03/x-20-jack --target-repo ../target-repo --repo-owner guchengwei --repo-name x-reader
```

Expected:
- bundle exists under `content-out/`
- target repo gets `content/...` and `site/d/<slug>/index.html`
- source bundle `publish.json` has `published: true`
- `public_url` is filled
- `revision` is filled

---

## Plan review checklist

Before implementation, verify:
- [ ] Tasks stay focused on publish workflow only
- [ ] No search/ASR/index creep
- [ ] Tests cover both source and target metadata updates
- [ ] Target repo git assumptions are explicit
- [ ] Workflow deploys already-rendered `site/` only
- [ ] TDD sequence is explicit for each code task
