from xfetch.config import PublishTargetConfig


def build_pages_url(config: PublishTargetConfig, slug: str) -> str:
    return f"https://{config.repo_owner}.github.io/{config.repo_name}/d/{slug}/"
