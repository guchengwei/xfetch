from pathlib import Path
import subprocess

from xfetch.config import PublishTargetConfig
from xfetch.publishing.git_publish import publish_repo
from xfetch.publishing.url import build_pages_url


def test_build_pages_url_for_project_pages_repo():
    cfg = PublishTargetConfig(repo_owner="guchengwei", repo_name="link-vault")
    url = build_pages_url(cfg, slug="x-123-alice")
    assert url == "https://guchengwei.github.io/link-vault/d/x-123-alice/"



def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()



def test_publish_repo_commits_and_pushes_to_local_remote(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True)

    target_repo = tmp_path / "target-repo"
    subprocess.run(["git", "init", str(target_repo)], check=True)
    _git("config", "user.name", "Hermes Agent", cwd=target_repo)
    _git("config", "user.email", "hermes@example.com", cwd=target_repo)
    _git("remote", "add", "origin", str(remote), cwd=target_repo)
    (target_repo / "README.md").write_text("hello\n", encoding="utf-8")

    revision = publish_repo(target_repo, branch="main", commit_message="publish: x-123-alice")

    assert revision
    assert _git("rev-parse", "HEAD", cwd=target_repo) == revision
    remote_head = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert remote_head == revision
