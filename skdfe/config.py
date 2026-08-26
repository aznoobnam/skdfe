"""Shared configuration and repository-relative paths."""

from dataclasses import dataclass
from pathlib import Path
import re

BASE_URL = "http://www.chillyroom.com/zh"
APK_REGEX = re.compile(
    r"https://pages.chillyroom.com/GameOfficialWebsite/strapi-cms/\w+_Soul_Knight_release_chillyroom_([_\d]+)_\w+\.apk"
)
ASSET_STUDIO_CLI_URL = (
    "https://github.com/aelurum/AssetStudio/releases/download/"
    "v0.18.0/AssetStudioModCLI_net6_win64.zip"
)
LANGUAGES = (
    "English", "Chinese (Traditional)", "Chinese (Simplified)", "Japanese",
    "Korean", "Spanish", "German", "Portuguese", "French", "Russian",
    "Polish", "Persian", "Arabic", "Thai", "Vietnamese",
)
XOR_KEY = b"soulKnight"
ITEM_PREFIX_GROUPS = (
    ("material_weapon_fragment", "material", "weapon_fragment"),
    ("material_skin_fragment", "material", "skin_fragment"),
    ("customization_kill_effect", "customization", "kill_effect"),
    ("blueprint_evolution", "blueprint", "evolution"),
    ("blueprint_weapon", "blueprint", "weapon"),
    ("blueprint_skin", "blueprint", "skin"),
    ("blueprint_skill", "blueprint", "skill"),
    ("blueprint_multi", "blueprint", "multi"),
    ("material_activity", "material", "activity"),
    ("material_skill", "material", "skill"),
    ("material_tape", "material", "tape"),
    ("blueprint_m", "blueprint", "m"),
)


@dataclass(frozen=True)
class ProjectPaths:
    """Filesystem locations used by the extraction pipeline."""

    root: Path

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def export_dir(self) -> Path:
        return self.data_dir / "export"

    @property
    def config_export_dir(self) -> Path:
        return self.data_dir / "config_export"

    @property
    def asset_studio_zip(self) -> Path:
        return self.data_dir / "AssetStudio.zip"

    @property
    def asset_studio_dir(self) -> Path:
        return self.data_dir / "AssetStudio"

    def apk_file(self, version: str) -> Path:
        return self.data_dir / f"sk-{version}.apk"

    def apk_dir(self, version: str) -> Path:
        return self.data_dir / f"sk-{version}"

    def output(self, name: str) -> Path:
        """Return a stable public artifact path."""
        return self.root / name
