"""Character sprite extraction from skin asset bundles."""

import logging
import re
import shutil
from pathlib import Path

from .assetstudio import run_asset_studio_cli
from .config import ProjectPaths

_SKIN_BUNDLE = re.compile(r"^skin_(\d+)\.ab$", re.I)


def _find_skin_bundles(
    sk_extracted_path: Path, codename: str
) -> list[tuple[int, Path]]:
    """Find all skin_X.ab bundles for a character, returning (index, path)."""
    skin_dir = (
        sk_extracted_path
        / "assets/AssetBundles/skin/character"
        / codename
    )
    if not skin_dir.is_dir():
        return []
    bundles = []
    for path in skin_dir.iterdir():
        match = _SKIN_BUNDLE.match(path.name)
        if match and path.is_file():
            bundles.append((int(match.group(1)), path))
    bundles.sort(key=lambda item: item[0])
    return bundles


def _try_export_sprite(
    asset_studio_dir: Path,
    bundle_path: Path,
    work_dir: Path,
    extra_args: tuple[str, ...],
) -> list[Path]:
    """Export Sprite assets and return exported PNGs, or [] on failure."""
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    try:
        run_asset_studio_cli(
            asset_studio_dir,
            bundle_path,
            work_dir,
            asset_type="sprite",
            mode="export",
            filter_name="",
            extra_args=("-g", "none") + extra_args,
        )
    except RuntimeError:
        return []
    return list(work_dir.rglob("*.png"))


def _pick_by_name(pngs: list[Path], target_stem: str) -> Path | None:
    """Pick the PNG whose stem matches target_stem case-insensitively."""
    target = target_stem.lower()
    for p in pngs:
        if p.stem.lower() == target:
            return p
    return None


def extract_character_sprites(
    paths: ProjectPaths,
    sk_extracted_path: Path,
    asset_studio_dir: Path,
    codenames: list[str],
) -> Path:
    """Extract the first idle-animation frame for all characters and skins.

    Output: character_sprite/<codename>/skin_<X>.png

    The first idle frame is the Sprite asset named ``{codename}_{skin_index}_0``.
    Uses a three-pass strategy per bundle:
    1. ``--filter-by-name {Codename}_{idx}_0`` — exports the exact sprite
       (case-insensitive substring); pick by exact name from results.
    2. ``--filter-by-container skin_{idx}/skin_{idx}_idle.anim`` (lowercase)
       — for skins with misnamed assets; pick the lowest-numbered frame.
    3. Export all sprites unfiltered — pick by exact name or lowest-numbered
       frame as last resort.

    Skin index X comes from the bundle filename, not the asset name.
    """
    output_root = paths.output("character_sprite")
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    work_dir = paths.data_dir / "sprite_export_tmp"
    extracted = 0

    for codename in codenames:
        bundles = _find_skin_bundles(sk_extracted_path, codename)
        if not bundles:
            logging.warning("No skin bundles found for %s", codename)
            continue

        char_dir = output_root / codename
        char_dir.mkdir(parents=True, exist_ok=True)

        for skin_index, bundle_path in bundles:
            result_png = None
            target_stem = f"{codename}_{skin_index}_0"

            # Pass 1: filter by sprite name
            pngs = _try_export_sprite(
                asset_studio_dir, bundle_path, work_dir,
                ("--filter-by-name", target_stem),
            )
            if pngs:
                result_png = _pick_by_name(pngs, target_stem)

            # Pass 2: fallback to idle container filter (lowercase)
            if result_png is None:
                container_filter = (
                    f"assets/skin/character/{codename.lower()}/"
                    f"skin_{skin_index}/skin_{skin_index}_idle.anim"
                )
                pngs = _try_export_sprite(
                    asset_studio_dir, bundle_path, work_dir,
                    ("--filter-by-container", container_filter),
                )
                if pngs:
                    result_png = _pick_by_name(pngs, target_stem)
                    if result_png is None:
                        result_png = _pick_lowest_frame(pngs)

            # Pass 3: export all sprites, pick by name or lowest frame
            if result_png is None:
                pngs = _try_export_sprite(
                    asset_studio_dir, bundle_path, work_dir, (),
                )
                if pngs:
                    result_png = _pick_by_name(pngs, target_stem)
                    if result_png is None:
                        result_png = _pick_lowest_frame(pngs)

            if result_png is None:
                logging.debug(
                    "No idle frame for %s skin_%d",
                    codename, skin_index,
                )
                continue

            dest = char_dir / f"skin_{skin_index}.png"
            shutil.copy2(result_png, dest)
            extracted += 1
            logging.info("Extracted %s/skin_%d.png", codename, skin_index)

    if work_dir.exists():
        shutil.rmtree(work_dir)

    logging.info(
        "Character sprite extraction complete: %d sprites in %s",
        extracted, output_root,
    )
    return output_root


def _pick_lowest_frame(pngs: list[Path]) -> Path | None:
    """Pick the PNG with the lowest trailing numeric suffix."""
    best = None
    best_num = float("inf")
    for p in pngs:
        match = re.search(r"_(\d+)$", p.stem)
        if match:
            num = int(match.group(1))
            if num < best_num:
                best_num = num
                best = p
    return best
