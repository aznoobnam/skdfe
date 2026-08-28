"""Soul Knight data extraction entrypoint."""

import logging
import sys
from pathlib import Path

from skdfe.acquisition import ensure_apk_extracted, ensure_asset_studio, get_latest_apk_info
from skdfe.assetstudio import find_valid_i2_dat, find_weapon_info, run_asset_extractions
from skdfe.code_names import discover_pet_sources, generate_char_code_names
from skdfe.config import ProjectPaths
from skdfe.config_exports import decrypt_config_exports
from skdfe.derivations import build_dictionaries, build_needed_data, build_weapon_evo_data
from skdfe.i2 import load_language_maps, parse_i2_asset_file, write_i2_csv
from skdfe.rendering import load_weapon_info, write_json, write_master_txt, write_weapon_full

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)


def main(root: Path | None = None) -> None:
    """Run all extraction stages with explicit repository paths."""
    paths = ProjectPaths(root or Path(__file__).parent.resolve())
    try:
        version, link = get_latest_apk_info()
    except Exception as error:
        logging.error("Failed to get APK info: %s", error)
        sys.exit(1)
    try:
        sk_extracted = ensure_apk_extracted(paths, version, link)
    except Exception as error:
        logging.error("Failed to download/extract APK: %s", error)
        sys.exit(1)
    try:
        asset_studio_dir = ensure_asset_studio(paths)
    except Exception as error:
        logging.error("Failed to prepare AssetStudio CLI: %s", error)
        sys.exit(1)
    try:
        generate_char_code_names(paths, sk_extracted, asset_studio_dir)
    except Exception as error:
        logging.error("Character code generation failed: %s", error)
        sys.exit(1)
    try:
        discover_pet_sources(paths, sk_extracted)
    except Exception as error:
        logging.warning("Pet source discovery failed: %s", error)
    try:
        run_asset_extractions(paths, sk_extracted, asset_studio_dir)
    except Exception as error:
        logging.error("AssetStudio extraction failed: %s", error)
        sys.exit(1)
    try:
        decrypt_config_exports(paths)
    except Exception as error:
        logging.error("Config export failed: %s", error)
        sys.exit(1)
    try:
        i2_dat = find_valid_i2_dat(paths.export_dir)
        records, _ = parse_i2_asset_file(i2_dat)
    except Exception as error:
        logging.error("Failed to parse I2 .dat: %s", error)
        sys.exit(1)
    try:
        csv_path = write_i2_csv(paths, records)
    except Exception as error:
        logging.error("Failed writing CSV: %s", error)
        sys.exit(1)
    try:
        weapon_info_path = find_weapon_info(paths.export_dir)
    except Exception as error:
        logging.error("Error locating WeaponInfo.txt: %s", error)
        sys.exit(1)
    try:
        language_maps = load_language_maps(csv_path, ("English", "Chinese (Simplified)"))
        lang_maps = build_dictionaries(language_maps["English"])
    except Exception as error:
        logging.error("Failed building language dictionaries: %s", error)
        sys.exit(1)
    try:
        weapon_info = load_weapon_info(weapon_info_path)
        out_txt = write_master_txt(paths, weapon_info.get("weapons", []), lang_maps)
        write_weapon_full(weapon_info, paths.output("weapon_full.json"))
        logging.info("All info fully baked: %s", out_txt)
    except Exception as error:
        logging.error("Failed baking all info file: %s", error)
        sys.exit(1)
    try:
        weapon_skin_path = paths.output("weapon_skins.json")
        write_json(build_weapon_evo_data(language_maps["English"]), weapon_skin_path, "weapon skins data")
        logging.info("Weapon evolution data baked : %s", weapon_skin_path)
    except Exception as error:
        logging.error("Cannot export weapon skin: %s", error)
    try:
        write_json(build_needed_data(language_maps["English"]), paths.output("needed_data.json"), "needed data")
        write_json(build_needed_data(language_maps["Chinese (Simplified)"]), paths.output("needed_data_cn.json"), "needed data")
        logging.info("Exported needed data for English and Chinese")
    except Exception as error:
        logging.warning("Can't export: %s", error)
    try:
        if paths.data_dir.exists():
            logging.info("Cleaned up data folder: %s", paths.data_dir)
    except Exception as error:
        logging.warning("Could not remove data folder (maybe in use): %s: %s", paths.data_dir, error)
    logging.info("All done.")


if __name__ == "__main__":
    main()
