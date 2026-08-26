"""Pure transformations from localization maps to wiki data."""

import re
from collections import defaultdict


def build_dictionaries(lang_map: dict[str, str]) -> dict[str, dict]:
    """Build categorized lookup dictionaries from resolved English strings."""
    weapons_map = {}
    buff_names, buff_infos = {}, {}
    challenge_names, challenge_titles, challenge_descs = {}, {}, {}
    materials, plants, pets = {}, {}, {}
    characters: dict[str, dict[str, str]] = {}
    for rid, value in lang_map.items():
        if rid.startswith("weapon/"):
            weapons_map[rid.replace("weapon/", "")] = value
        elif rid.startswith("Buff_name_"):
            buff_names[rid] = value
        elif rid.startswith("Buff_info_"):
            buff_infos[rid] = value
        elif rid.startswith("task/"):
            match = re.match(r"task/([^_]+)(_title|_desc)?", rid)
            if not match:
                continue
            cid, suffix = match.groups()
            if suffix == "_title":
                challenge_titles[cid] = value
            elif suffix == "_desc":
                challenge_descs[cid] = value
            else:
                challenge_names[cid] = value
        elif rid.startswith("material_"):
            materials[rid] = value
        elif rid.startswith("plant_") and "/" not in rid:
            plants[rid] = value
        elif rid.startswith("Pet_name_") and not rid.endswith(("_des", "_lock")):
            pets[rid] = value
        else:
            match = re.match(r"Character(\d+)_name_skin(\d+)", rid)
            if match:
                char_index, skin_index = match.groups()
                characters.setdefault(char_index, {})[skin_index] = value
    return {
        "weapons": weapons_map,
        "buff_names": buff_names,
        "buff_infos": buff_infos,
        "challenge_names": challenge_names,
        "challenge_titles": challenge_titles,
        "challenge_descs": challenge_descs,
        "materials": materials,
        "plants": plants,
        "pets": pets,
        "characters": characters,
    }


def build_weapon_evo_data(lang_map: dict[str, str]) -> dict:
    """Build the game-save-shaped weapon evolution structure."""
    skin_pattern = re.compile(r"^(weapon_\w+)_s_\d+$")
    upgrade_pattern = re.compile(r"^desc_evolution_(weapon_\w+)$")
    weapon_skin_map = defaultdict(list)
    upgradable_weapons = set()
    for key in lang_map:
        if "/" in key:
            continue
        skin_match = skin_pattern.match(key)
        if skin_match:
            weapon_skin_map[skin_match.group(1)].append(key)
            continue
        upgrade_match = upgrade_pattern.match(key)
        if upgrade_match:
            upgradable_weapons.add(upgrade_match.group(1))
    weapon_skin_map = {key: sorted(value) for key, value in weapon_skin_map.items()}
    upgradable = sorted(upgradable_weapons)
    return {
        "blindBoxOpenCount0": 0,
        "favorWeapons": [],
        "lastOpenMachineHistoryStr0": "",
        "weapons": {
            weapon: {
                "Name": weapon,
                "Level": 1 if weapon in upgradable else 0,
                "CurrentSkinIndex": 1 if (skins := weapon_skin_map.get(weapon)) else 0,
                "UnlockedSkins": skins or [],
            }
            for weapon in weapon_skin_map.keys() | upgradable_weapons
        },
    }


def build_needed_data(lang_map: dict[str, str]) -> dict:
    """Select localization entries consumed by the wiki."""
    result = {
        "skin": defaultdict(dict), "pet": {}, "material": {},
        "character_skill": {}, "weapon_skin": {},
    }
    patterns = {
        "skin": re.compile(r"Character(\d+)_name_skin(\d+)"),
        "pet": re.compile(r"Pet_name_(\d+)"),
        "material": re.compile(r"(^material_(?!.*(?:activity|book|skill|new|money|multi|desc)).*)"),
        "character_skill": re.compile(r"(Character\d+_skill_\d+_name)"),
        "weapon_skin": re.compile(r"(weapon_\w+_s_\d+)")
    }
    for key, value in lang_map.items():
        match = patterns["skin"].fullmatch(key)
        if match:
            char_index, skin_index = match.groups()
            result["skin"][f"c{char_index}"][f"c{char_index}_skin{skin_index}"] = value
            continue
        match = patterns["pet"].fullmatch(key)
        if match:
            result["pet"][match.group(1)] = value
            continue
        match = patterns["material"].fullmatch(key)
        if match:
            result["material"][match.group(1)] = value
            continue
        match = patterns["character_skill"].fullmatch(key)
        if match:
            result["character_skill"][match.group(1)] = value
            continue
        match = patterns["weapon_skin"].fullmatch(key)
        if match:
            result["weapon_skin"][match.group(1)] = value
    result["skin"] = dict(result["skin"])
    return result
