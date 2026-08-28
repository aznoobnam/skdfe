"""Authoritative internal character code-name extraction."""

import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

from .assetstudio import run_asset_studio_cli
from .config import ProjectPaths

_CHARACTER_PREFAB = re.compile(r"^-\s+Assets/RGPrefab/Player/c(\d+)\.prefab$", re.I)
_DUMP_NAME = re.compile(r'^\s*string m_Name = "CharacterSprites"\s*$', re.M)
_MODEL = re.compile(
    r"CharacterSpriteModel data\s+int characterIndex = (\d+)\s+"
    r"int skinIndex = (\d+)(.*?)(?=\n\s*(?:\[\d+\]\s*\n\s*)?"
    r"CharacterSpriteModel data|\Z)", re.S
)
_SPRITE_PATH = re.compile(r'string path = "Skin/Character/([^/]+)/Skin_(\d+)/', re.I)
_PET_PREFAB = re.compile(r"^-\s+((?=[^\n]*pet).+\.prefab)$", re.I)


def read_hero_character_ids(manifest_path: Path) -> list[int]:
    """Read contiguous numeric character IDs from hero.manifest."""
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Character manifest not found: {manifest_path}")
    ids = [
        int(match.group(1))
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if (match := _CHARACTER_PREFAB.fullmatch(line.strip()))
    ]
    if not ids:
        raise ValueError(f"No character prefabs found in {manifest_path}")
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate character ID in {manifest_path}")
    ids.sort()
    expected = list(range(len(ids)))
    if ids != expected:
        raise ValueError(f"Character IDs are not contiguous: {ids}")
    return ids


def find_character_sprites_dump(dump_dir: Path) -> Path:
    """Find exactly one text dump whose root object is CharacterSprites."""
    matches = []
    for path in sorted(dump_dir.rglob("*.txt")):
        try:
            if _DUMP_NAME.search(path.read_text(encoding="utf-8", errors="replace")):
                matches.append(path)
        except OSError as error:
            raise RuntimeError(f"Could not read CharacterSprites dump {path}: {error}") from error
    if len(matches) != 1:
        raise ValueError(f"Expected one CharacterSprites dump; found {len(matches)}")
    return matches[0]


def read_character_code_names(dump_dir: Path, expected_ids: list[int]) -> list[str]:
    """Parse base-skin rows and return names ordered by numeric character ID."""
    dump_path = find_character_sprites_dump(dump_dir)
    text = dump_path.read_text(encoding="utf-8", errors="replace")
    names: dict[int, str] = {}
    for character_id_text, skin_index, body in _MODEL.findall(text):
        if skin_index != "0":
            continue
        character_id = int(character_id_text)
        paths = {
            name for name, path_skin_index in _SPRITE_PATH.findall(body)
            if path_skin_index == "0" and name
        }
        if len(paths) != 1:
            raise ValueError(
                f"Character {character_id} base skin has {len(paths)} code names"
            )
        if character_id in names:
            raise ValueError(f"Duplicate base-skin row for character {character_id}")
        names[character_id] = paths.pop()

    if set(names) != set(expected_ids):
        missing = sorted(set(expected_ids) - set(names))
        extra = sorted(set(names) - set(expected_ids))
        raise ValueError(f"CharacterSprites IDs do not match hero manifest: missing={missing}, extra={extra}")
    ordered = [names[character_id] for character_id in expected_ids]
    if len(ordered) != len(set(ordered)):
        raise ValueError("Character code names are not unique")
    return ordered


def write_json_atomic(output_path: Path, value: object) -> None:
    """Write formatted JSON through an atomic same-directory replacement."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", delete=False,
            dir=output_path.parent, prefix=f".{output_path.name}."
        ) as temporary:
            temporary.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.replace(temporary_name, output_path)
        temporary_name = None
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def generate_char_code_names(
    paths: ProjectPaths, sk_extracted_path: Path, asset_studio_dir: Path
) -> Path:
    """Extract CharacterSprites and publish ordered char_code_name.json."""
    bundle_root = sk_extracted_path / "assets/AssetBundles"
    common_bundle = bundle_root / "common.ab"
    hero_manifest = bundle_root / "hero.manifest"
    for path in (common_bundle, hero_manifest):
        if not path.is_file():
            raise FileNotFoundError(f"Character extraction input missing: {path}")

    character_ids = read_hero_character_ids(hero_manifest)
    if paths.character_dump_dir.exists():
        shutil.rmtree(paths.character_dump_dir)
    run_asset_studio_cli(
        asset_studio_dir,
        common_bundle,
        paths.character_dump_dir,
        "monobehaviour",
        "dump",
        "CharacterSprites",
        extra_args=("-g", "none", "-f", "pathID"),
    )
    names = read_character_code_names(paths.character_dump_dir, character_ids)
    output_path = paths.output("char_code_name.json")
    write_json_atomic(output_path, names)
    logging.info("Generated character code names: %s", output_path)
    return output_path


def collect_pet_manifest_candidates(bundle_root: Path) -> list[dict[str, object]]:
    """Collect pet-like prefab manifest evidence without inferring names."""
    candidates = []
    for manifest in sorted(bundle_root.rglob("*.manifest")):
        try:
            prefab_paths = sorted({
                match.group(1).replace("\\", "/")
                for line in manifest.read_text(encoding="utf-8").splitlines()
                if (match := _PET_PREFAB.fullmatch(line.strip()))
            })
        except OSError as error:
            logging.warning("Could not read pet candidate manifest %s: %s", manifest, error)
            continue
        if not prefab_paths:
            continue
        companion = manifest.with_suffix(".ab")
        candidates.append({
            "manifest": manifest.relative_to(bundle_root.parent).as_posix(),
            "pet_prefab_paths": prefab_paths,
            "companion_bundle": (
                companion.relative_to(bundle_root.parent).as_posix()
                if companion.is_file() else None
            ),
        })
    return candidates


def discover_pet_sources(paths: ProjectPaths, sk_extracted_path: Path) -> Path | None:
    """Record unverified pet-source candidates; never publish pet names."""
    bundle_root = sk_extracted_path / "assets/AssetBundles"
    if not bundle_root.is_dir():
        logging.warning("AssetBundle directory missing; skipping pet discovery: %s", bundle_root)
        return None
    report = {
        "status": "unverified",
        "manifest_candidates": collect_pet_manifest_candidates(bundle_root),
    }
    write_json_atomic(paths.pet_discovery_path, report)
    logging.info("Wrote unverified pet source discovery: %s", paths.pet_discovery_path)
    return paths.pet_discovery_path
