from xfetch.config import PublishTargetConfig
from xfetch.publishing.url import build_pages_url


def test_build_pages_url_for_project_pages_repo():
    cfg = PublishTargetConfig(repo_owner="guchengwei", repo_name="x-reader")
    url = build_pages_url(cfg, slug="x-123-alice")
    assert url == "https://guchengwei.github.io/x-reader/d/x-123-alice/"
