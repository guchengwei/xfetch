from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(slots=True)
class RuntimeConfig:
    content_root: Path
    site_root: Path
    timezone: str = "UTC"
    runtime_version: str = "0.1.0"
    publish_branch: str = "main"
    site_subdir: str = "site"


@dataclass(slots=True)
class PublishTargetConfig:
    repo_owner: str
    repo_name: str
    branch: str = "main"
    content_subdir: str = "content"
    site_subdir: str = "site"


def _resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def load_config(content_root: str | Path | None = None, site_root: str | Path | None = None) -> RuntimeConfig:
    raw_content = content_root or os.environ.get("XFETCH_CONTENT_ROOT") or "content-out"
    raw_site = site_root or os.environ.get("XFETCH_SITE_ROOT") or "site-out"
    return RuntimeConfig(
        content_root=_resolve_path(raw_content),
        site_root=_resolve_path(raw_site),
    )
