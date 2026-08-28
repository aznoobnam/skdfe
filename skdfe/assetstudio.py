"""AssetStudio CLI invocation and exported-asset discovery."""

import logging
import shutil
import subprocess
from pathlib import Path

from .config import ProjectPaths


def run_asset_studio_cli(
    asset_studio_dir: Path,
    unity_data_path: Path,
    output_dir: Path,
    asset_type: str,
    mode: str,
    filter_name: str,
    assembly_folder: Path | None = None,
    extra_args: tuple[str, ...] = (),
) -> None:
    """Invoke AssetStudioModCLI using the established command contract."""
    if not unity_data_path.exists():
        raise FileNotFoundError(f"Unity data file not found: {unity_data_path}")
    executable = asset_studio_dir / "AssetStudioModCLI.exe"
    if not executable.exists():
        executable = asset_studio_dir / "AssetStudioModCLI"
        if not executable.exists():
            raise FileNotFoundError(f"AssetStudioModCLI not found in {asset_studio_dir}")
    command = [
        str(executable), str(unity_data_path), "-t", asset_type, "-m", mode,
        "-o", str(output_dir), "--filter-by-name", filter_name,
    ]
    if assembly_folder:
        if not assembly_folder.exists() or not assembly_folder.is_dir():
            raise FileNotFoundError(f"Assembly folder not found: {assembly_folder}")
        command.extend(["--assembly-folder", str(assembly_folder)])
    command.extend(extra_args)
    logging.info("Running AssetStudioModCLI: %s", " ".join(command))
    try:
        subprocess.run(command, check=True, cwd=asset_studio_dir)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"AssetStudioModCLI failed (exit code {error.returncode})"
        ) from error
    logging.info("AssetStudio CLI finished extracting %s.", asset_type)


def run_asset_extractions(
    paths: ProjectPaths, sk_extracted_path: Path, asset_studio_dir: Path
) -> None:
    """Refresh I2, WeaponInfo, and encrypted config exports."""
    unity_data = sk_extracted_path / "assets/bin/Data/data.unity3d"
    managed_folder = sk_extracted_path / "assets/bin/Data/Managed"
    config_bundle = sk_extracted_path / "assets/AssetBundles/config.ab"
    if not unity_data.exists():
        raise FileNotFoundError(f"Unity data file missing: {unity_data}")
    if not managed_folder.exists() or not managed_folder.is_dir():
        raise FileNotFoundError(f"Managed folder missing: {managed_folder}")
    if not config_bundle.exists():
        raise FileNotFoundError(f"Config asset bundle missing: {config_bundle}")

    try:
        paths.export_dir.mkdir(parents=True, exist_ok=True)
        for dat_file in paths.export_dir.rglob("I2Languages*.dat"):
            dat_file.unlink()
    except Exception as error:
        raise RuntimeError(
            f"Could not refresh I2 exports under {paths.export_dir}: {error}"
        ) from error

    run_asset_studio_cli(
        asset_studio_dir, unity_data, paths.export_dir, "monobehaviour", "raw",
        "i2language", managed_folder,
    )
    removed_any = False
    for dat_file in paths.export_dir.rglob("I2Languages*.dat"):
        try:
            size = dat_file.stat().st_size
        except OSError as error:
            logging.warning("Could not stat file %s: %s", dat_file, error)
            continue
        if size < 2_000_000:
            try:
                dat_file.unlink()
                logging.info("Removed SMALL I2 file: %s (%s bytes)", dat_file.name, size)
                removed_any = True
            except Exception as error:
                logging.warning("Failed to remove %s: %s", dat_file, error)
    if not removed_any:
        logging.info("No SMALL I2Languages*.dat files were found to remove.")

    run_asset_studio_cli(
        asset_studio_dir, unity_data, paths.export_dir, "textasset", "export", "WeaponInfo"
    )
    for asset_name in ("enemies.csv", "items.csv"):
        output_dir = paths.config_export_dir / Path(asset_name).stem
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True)
        run_asset_studio_cli(
            asset_studio_dir, config_bundle, output_dir, "textasset", "export",
            Path(asset_name).stem,
        )


def find_valid_i2_dat(export_dir: Path) -> Path:
    """Find the canonical or sole large I2Languages export."""
    candidates = []
    for dat_file in sorted(export_dir.rglob("I2Languages*.dat")):
        try:
            if dat_file.stat().st_size >= 2_000_000:
                candidates.append(dat_file)
        except OSError:
            continue
    if not candidates:
        raise FileNotFoundError("No valid (≥2 MB) I2Languages .dat file found under export/.")
    canonical = [path for path in candidates if path.name == "I2Languages.dat"]
    if len(canonical) == 1:
        selected = canonical[0]
    elif len(candidates) == 1:
        selected = candidates[0]
    else:
        paths = ", ".join(str(path) for path in candidates)
        raise RuntimeError(f"Ambiguous I2Languages exports: {paths}")
    logging.info("Found valid I2 dat: %s (%s bytes)", selected.name, selected.stat().st_size)
    return selected


def find_exported_text_asset(output_dir: Path, asset_name: str) -> Path:
    """Find one AssetStudio TextAsset export by its original name."""
    accepted_names = {asset_name.lower(), f"{asset_name.lower()}.txt"}
    matches = [
        path for path in output_dir.rglob("*")
        if path.is_file() and path.name.lower() in accepted_names
    ]
    if len(matches) != 1:
        found = ", ".join(str(path) for path in matches) or "none"
        raise FileNotFoundError(
            f"Expected one export for {asset_name} under {output_dir}; found: {found}"
        )
    return matches[0]


def find_weapon_info(export_dir: Path) -> Path:
    """Locate WeaponInfo using the historical top-level export lookup."""
    for path in export_dir.iterdir():
        if path.name.lower().endswith("weaponinfo.txt"):
            return path
    raise FileNotFoundError("WeaponInfo.txt not found under export/")
