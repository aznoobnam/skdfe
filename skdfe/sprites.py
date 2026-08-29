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


def _export_sprites(
    asset_studio_dir: Path,
    bundle_path: Path,
    work_dir: Path,
    extra_args: tuple[str, ...] = (),
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


def _pick_frame(pngs: list[Path], codename: str, skin_index: int) -> Path | None:
    """Pick the best idle frame from exported PNGs.

    Tries exact name match first, then falls back to lowest numeric suffix.
    """
    result = _pick_by_name(pngs, f"{codename}_{skin_index}_0")
    if result is None:
        result = _pick_lowest_frame(pngs)
    return result


# Container filter strategies, tried in priority order.
# Each returns a tuple of extra_args for AssetStudio CLI.
# Container paths inside bundles are always lowercase.
def _container_strategies(codename: str, skin_index: int) -> list[tuple[str, ...]]:
    """Return container filter args in priority order."""
    lower = codename.lower()
    prefix = f"assets/skin/character/{lower}/skin_{skin_index}"
    return [
        # 1. Exact idle animation
        ("--filter-by-container", f"{prefix}/skin_{skin_index}_idle.anim"),
        # 2. Any idle-related container (idle_long, idle_skill, idle_charge, etc.)
        # AssetStudio filter is substring match, so "idle" in the prefix catches variants
        ("--filter-by-container", f"{prefix}/skin_{skin_index}_idle"),
        # 3. Run animation
        ("--filter-by-container", f"{prefix}/skin_{skin_index}_run.anim"),
        # 4. PNG sprite sheet container (sprite-sheet-only skins)
        ("--filter-by-container", f"{prefix}/{lower}"),
    ]


def extract_character_sprites(
    paths: ProjectPaths,
    sk_extracted_path: Path,
    asset_studio_dir: Path,
    codenames: list[str],
) -> Path:
    """Extract the first idle-animation frame for all characters and skins.

    Output: character_sprite/<codename>/skin_<X>.png

    Prioritises accuracy by filtering on container path (which animation
    the sprite belongs to) rather than on asset name alone.  Container
    strategies are tried in order:

    1. Exact ``skin_X_idle.anim`` container — the canonical idle animation.
    2. Any ``skin_X_idle*`` container — catches ``idle_long``, ``idle_skill``,
       ``idle_charge`` variants.
    3. Exact ``skin_X_run.anim`` — skins that have no idle sprites.
    4. ``.png`` sprite-sheet container — skins whose sprites are not
       referenced by any ``.anim``.
    5. Export all sprites unfiltered — last resort.

    At each step the first idle frame is selected by exact name
    ``{codename}_{skin_index}_0`` (case-insensitive), falling back to the
    sprite with the lowest numeric suffix.

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

            # Try each container strategy in priority order
            for extra_args in _container_strategies(codename, skin_index):
                pngs = _export_sprites(
                    asset_studio_dir, bundle_path, work_dir, extra_args,
                )
                if pngs:
                    result_png = _pick_frame(pngs, codename, skin_index)
                    if result_png is not None:
                        break

            # Last resort: export all sprites unfiltered
            if result_png is None:
                pngs = _export_sprites(
                    asset_studio_dir, bundle_path, work_dir,
                )
                if pngs:
                    result_png = _pick_frame(pngs, codename, skin_index)

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
