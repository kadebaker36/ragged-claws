"""Portable local-data path conventions."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataLayout:
    """All local storage paths rooted below one caller-selected directory."""

    root: Path

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def raw_objects(self) -> Path:
        return self.raw / "objects"

    @property
    def raw_manifests(self) -> Path:
        return self.raw / "manifests"

    @property
    def staging(self) -> Path:
        return self.root / "staging"

    @property
    def curated(self) -> Path:
        return self.root / "curated"

    @property
    def research(self) -> Path:
        return self.root / "research"

    @property
    def snapshots(self) -> Path:
        return self.root / "snapshots"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def catalog(self) -> Path:
        return self.cache / "catalog.duckdb"

    def create(self) -> None:
        """Create the documented layout without relying on platform-specific paths."""
        for path in (
            self.raw_objects,
            self.raw_manifests,
            self.staging,
            self.curated,
            self.research,
            self.snapshots,
            self.cache,
        ):
            path.mkdir(parents=True, exist_ok=True)
