"""Wiki artifact rendering."""

import json
import logging
from pathlib import Path

from .config import ProjectPaths


def load_weapon_info(weapon_info_path: Path) -> dict:
    """Load the complete WeaponInfo JSON once for dependent outputs."""
    if not weapon_info_path.exists():
        raise FileNotFoundError(f"WeaponInfo JSON not found: {weapon_info_path}")
    try:
        with weapon_info_path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Invalid JSON in {weapon_info_path}: {error}") from error
    except Exception as error:
        raise RuntimeError(f"Failed reading {weapon_info_path}: {error}") from error


def write_master_txt(
    paths: ProjectPaths, weapons: list[dict], lang_maps: dict[str, dict]
) -> Path:
    """Write the historical human-readable master report."""
    txt_path = paths.output("Allinfo.txt")

    logging.info("Writing master TXT: %s", txt_path)
    weapons_sorted = sorted(weapons, key=lambda weapon: weapon.get("name", ""))
    max_skin_ids = {}
    try:
        with txt_path.open("w", encoding="utf-8") as out:
            out.write(
                "██     ██ ███████  █████  ██████   ██████  ███    ██\n"
                "██     ██ ██      ██   ██ ██   ██ ██    ██ ████   ██\n"
                "██  █  ██ █████   ███████ ██████  ██    ██ ██ ██  ██\n"
                "██ ███ ██ ██      ██   ██ ██      ██    ██ ██  ██ ██\n"
                " ███ ███  ███████ ██   ██ ██       ██████  ██   ████\n\n"
            )
            for weapon in weapons_sorted:
                name_key = weapon.get("name", "")
                out.write(f"{name_key}\n")
                out.write(f"    Name      : {lang_maps['weapons'].get(name_key, '[Name Not Found]')}\n")
                out.write(f"    Forgeable : {weapon.get('forgeable', False)}\n")
                out.write(f"    Is melee  : {weapon.get('isMelle', False)}\n")
                out.write(f"    Rarity    : {weapon.get('level', '')}\n")
                out.write(f"    Type      : {weapon.get('type', '')}\n\n")

            out.write(
                " ██████ ██   ██  █████  ██████   █████   ██████ ████████ ███████ ██████\n"
                "██      ██   ██ ██   ██ ██   ██ ██   ██ ██         ██    ██      ██   ██\n"
                "██      ███████ ███████ ██████  ███████ ██         ██    █████   ██████\n"
                "██      ██   ██ ██   ██ ██   ██ ██   ██ ██         ██    ██      ██   ██\n"
                " ██████ ██   ██ ██   ██ ██   ██ ██   ██  ██████    ██    ███████ ██   ██\n\n"
            )
            for char_index in sorted(lang_maps["characters"]):
                skins = lang_maps["characters"][char_index]
                out.write(f"c{char_index} = {skins.get('0', '[Unknown]')}\n")
                max_skin_ids[f"c{char_index}"] = max(int(skin_id) for skin_id in skins)
                for skin_index in sorted(skins, key=int):
                    out.write(f"    c{char_index}_skin{skin_index} = {skins[skin_index]}\n")
                out.write("\n")

            out.write("██████  ███████ ████████\n"
                      "██   ██ ██         ██   \n"
                      "██████  █████      ██   \n"
                      "██      ██         ██   \n"
                      "██      ███████    ██   \n\n")
            for pet_id, pet_name in sorted(lang_maps["pets"].items()):
                out.write(f"{pet_id.removeprefix('Pet_name_')}\n")
                out.write(f"    Display name : {pet_name}\n\n")

            out.write("██████  ██    ██ ███████ ███████ \n"
                      "██   ██ ██    ██ ██      ██      \n"
                      "██████  ██    ██ █████   █████   \n"
                      "██   ██ ██    ██ ██      ██      \n"
                      "██████   ██████  ██      ██      \n\n")
            buff_ids = {
                key.replace("Buff_name_", "") for key in lang_maps["buff_names"]
            } | {key.replace("Buff_info_", "") for key in lang_maps["buff_infos"]}
            for buff_id in sorted(buff_ids):
                out.write(f"{buff_id}\n")
                out.write(f"    Name        : {lang_maps['buff_names'].get(f'Buff_name_{buff_id}', '[Name Not Found]')}\n")
                out.write(f"    Description : {lang_maps['buff_infos'].get(f'Buff_info_{buff_id}', '[Description Not Found]')}\n\n")

            out.write(
                " ██████ ██   ██  █████  ██       █████  ███    ██  ██████  ███████ \n"
                "██      ██   ██ ██   ██ ██      ██   ██ ████   ██ ██       ██      \n"
                "██      ███████ ███████ ██      ███████ ██ ██  ██ ██   ███ █████   \n"
                "██      ██   ██ ██   ██ ██      ██   ██ ██  ██ ██ ██    ██ ██      \n"
                " ██████ ██   ██ ██   ██ ███████ ██   ██ ██   ████  ██████  ███████ \n\n"
            )
            challenge_ids = set(lang_maps["challenge_names"]) | set(lang_maps["challenge_titles"]) | set(lang_maps["challenge_descs"])
            for challenge_id in sorted(challenge_ids, key=lambda value: int(value) if value.isdigit() else value):
                out.write(f"{challenge_id.removeprefix('name/')}\n")
                out.write(f"    Name        : {lang_maps['challenge_names'].get(challenge_id, '[Name Not Found]')}\n")
                out.write(f"    Title       : {lang_maps['challenge_titles'].get(challenge_id, '[Title Not Found]')}\n")
                out.write(f"    Description : {lang_maps['challenge_descs'].get(challenge_id, '[Description Not Found]')}\n\n")

            out.write("███    ███  █████  ████████ ███████ ██████  ██  █████  ██      \n"
                      "████  ████ ██   ██    ██    ██      ██   ██ ██ ██   ██ ██      \n"
                      "██ ████ ██ ███████    ██    █████   ██████  ██ ███████ ██      \n"
                      "██  ██  ██ ██   ██    ██    ██      ██   ██ ██ ██   ██ ██      \n"
                      "██      ██ ██   ██    ██    ███████ ██   ██ ██ ██   ██ ███████ \n\n")
            for material_id, material_name in sorted(lang_maps["materials"].items()):
                out.write(f"{material_id}\n")
                out.write(f"    Display name : {material_name}\n\n")

            out.write("██████  ██       █████  ███    ██ ████████ \n"
                      "██   ██ ██      ██   ██ ████   ██    ██    \n"
                      "██████  ██      ███████ ██ ██  ██    ██    \n"
                      "██      ██      ██   ██ ██  ██ ██    ██    \n"
                      "██      ███████ ██   ██ ██   ████    ██    \n\n")
            for plant_id, plant_name in sorted(lang_maps["plants"].items()):
                out.write(f"{plant_id}\n")
                out.write(f"    Display name : {plant_name}\n\n")
        skin_path = paths.root / "highest_skin_ids.json"
        with skin_path.open("w", encoding="utf-8") as file:
            json.dump(max_skin_ids, file, indent=2, sort_keys=True)
        logging.info("Exported max skin IDs to %s", skin_path)
    except Exception as error:
        raise RuntimeError(f"Failed writing master TXT {txt_path}: {error}") from error
    return txt_path


def write_weapon_full(weapon_info: dict, output_path: Path) -> None:
    """Write the complete AssetStudio WeaponInfo JSON payload."""
    try:
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(weapon_info, file, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as error:
        raise RuntimeError(f"Failed writing full weapon JSON: {error}") from error
    logging.info("Exported full weapon data: %s", output_path)


def write_json(data: object, output_path: Path, label: str) -> None:
    """Write existing pretty-printed JSON artifact format."""
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False, sort_keys=True)
    logging.info("Exported %s: %s", label, output_path)
