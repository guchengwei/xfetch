from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class PublishResult:
    bundle_destination_dir: Path
    site_destination_path: Path | None
    target_path: str
    published: bool = False
    public_url: str | None = None
    revision: str | None = None
