import re
import sys
import csv
import json
import time
import shutil
import logging
import zipfile
import requests
import subprocess
from pathlib import Path
from collections import defaultdict
from typing import List, Tuple, Dict

BASE_URL = "http://www.chillyroom.com/zh"
APK_REGEX = re.compile(
    r"https://apk\.chillyroom\.com/apks/[\w\d.\-]+/SoulKnight-release-chillyroom-([\w\d.\-]+)\.apk"
)

ASSET_STUDIO_CLI_URL = (
    "https://github.com/aelurum/AssetStudio/releases/download/"
    "v0.18.0/AssetStudioModCLI_net6_win64.zip")

LANGUAGES = [
    "English",
    "Chinese (Traditional)",
    "Chinese (Simplified)",
    "Japanese",
    "Korean",
    "Spanish",
    "German",
    "Portuguese",
    "French",
    "Russian",
    "Polish",
    "Persian",
    "Arabic",
    "Thai",
    "Vietnamese",
]

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"
EXPORT_DIR = DATA_DIR / "export"
ASSET_STUDIO_ZIP = DATA_DIR / "AssetStudio.zip"
ASSET_STUDIO_DIR = DATA_DIR / "AssetStudio"


def download_file(url: str, dest: Path, chunk_size: int = 8192) -> None:
    """
    Download `url` to `dest` with a custom progress bar, download speed, and ETA.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading: {url}")

    try:
        with requests.get(url, verify=False, stream=True, timeout=30) as resp:
            resp.raise_for_status()
            # total = int(resp.headers.get("content-length", 0))
            # downloaded = 0
            # bar_len = 50
            # start_time = time.time()

            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        # downloaded += len(chunk)
                        # elapsed = time.time() - start_time
                        # speed = downloaded / elapsed if elapsed > 0 else 0

                        # if total:
                        #     percent = downloaded / total
                        #     done = int(bar_len * percent)
                        #     bar = '█' * done + '-' * (bar_len - done)
                        #     eta = (total - downloaded) / speed if speed > 0 else 0
                        #     mins, secs = divmod(int(eta), 60)
                        #     eta_str = f"{mins:02}:{secs:02}"  # e.g. 01:25

                        #     sys.stdout.write(
                        #         f"\r[{bar}] {percent*100:5.1f}% "
                        #         f"{downloaded/1024/1024:6.2f} MB/{total/1024/1024:6.2f} MB "
                        #         f"{speed/1024/1024:5.2f} MB/s "
                        #         f"ETA: {eta_str}"
                        #     )
                        # else:
                        #     sys.stdout.write(
                        #         f"\rDownloaded {downloaded/1024/1024:6.2f} MB "
                        #         f"at {speed/1024/1024:5.2f} MB/s"
                        #     )

                        # sys.stdout.flush()
        print("\nDownload complete.")
    except Exception as e:
        raise RuntimeError(f"Failed to download {url}: {e}") from e


def extract_zip(zip_path: Path, target_dir: Path) -> None:
    """
    Extract a zipfile to `target_dir`.
    """
    if not zip_path.exists():
        raise FileNotFoundError(f"Zip file not found: {zip_path}")
    logging.info(f"Extracting zip: {zip_path} → {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(target_dir)
    except zipfile.BadZipFile as e:
        raise RuntimeError(f"Bad zip file {zip_path}: {e}") from e
    logging.info("Extraction complete.")


def run_asset_studio_cli(
    asset_studio_dir: Path,
    unity_data_path: Path,
    output_dir: Path,
    asset_type: str,
    mode: str,
    filter_name: str,
    assembly_folder: Path = None,
) -> None:
    """
    Invoke AssetStudioModCLI with subprocess.
    - `asset_type`: e.g. "monobehaviour" or "textasset"
    - `mode`: e.g. "raw" or "export"
    - `filter_name`: e.g. "i2language" or "WeaponInfo"
    - `assembly_folder`: required only for monobehaviour extraction.
    """
    if not unity_data_path.exists():
        raise FileNotFoundError(
            f"Unity data file not found: {unity_data_path}")

    executable = asset_studio_dir / "AssetStudioModCLI.exe"
    if not executable.exists():
        executable = asset_studio_dir / "AssetStudioModCLI"
        if not executable.exists():
            raise FileNotFoundError(
                f"AssetStudioModCLI not found in {asset_studio_dir}")

    cmd = [
        str(executable),
        str(unity_data_path),
        "-t",
        asset_type,
        "-m",
        mode,
        "-o",
        str(output_dir),
        "--filter-by-name",
        filter_name,
    ]
    if assembly_folder:
        if not assembly_folder.exists() or not assembly_folder.is_dir():
            raise FileNotFoundError(
                f"Assembly folder not found: {assembly_folder}")
        cmd.extend(["--assembly-folder", str(assembly_folder)])

    logging.info("Running AssetStudioModCLI: " + " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, cwd=asset_studio_dir)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"AssetStudioModCLI failed (exit code {e.returncode})") from e
    logging.info(f"AssetStudio CLI finished extracting {asset_type}.")


def sanitize_text(text: str) -> str:
    """
    Replace CRLF / CR / LF with literal '\n' and strip.
    """
    return text.replace("\r\n", "\\n").replace("\r",
                                               "\\n").replace("\n",
                                                              "\\n").strip()


def parse_i2_asset_file(
    file_path: Path,
    filter_patterns: List[re.Pattern] = None
) -> Tuple[List[Tuple[str, List[str]]], List[str]]:
    """
    Parse a single I2 Languages .dat file.
    Returns:
      - sorted list of (key, [fields...])
      - list of language names
    """
    if not file_path.exists():
        raise FileNotFoundError(f"I2 .dat file not found: {file_path}")

    data = file_path.read_bytes()
    records: List[Tuple[str, List[str]]] = []
    pos = 60

    while pos < len(data):

        if pos % 4:
            pos += 4 - (pos % 4)
        if pos + 4 > len(data):
            break

        key_len = int.from_bytes(data[pos:pos + 4], "little")
        pos += 4

        if key_len == 0:

            while (pos < len(data)
                   and int.from_bytes(data[pos:pos + 4], "little") == 0):
                pos += 4
            if pos >= len(data) - 4:
                break
            key_len = int.from_bytes(data[pos:pos + 4], "little")
            pos += 4
            if key_len == 0:
                break

        key_bytes = data[pos:pos + key_len]
        try:
            key = key_bytes.decode("utf-8", errors="ignore").strip()
        except UnicodeDecodeError:
            key = key_bytes.decode("latin-1", errors="ignore").strip()
        pos += key_len

        if pos % 4:
            pos += 4 - (pos % 4)

        if pos + 4 > len(data):
            break
        start_count = int.from_bytes(data[pos:pos + 4], "little")
        pos += 4

        if start_count == 0:
            if pos + 4 > len(data):
                break
            fields_count = int.from_bytes(data[pos:pos + 4], "little")
            pos += 4
        else:
            fields_count = start_count

        fields: List[str] = []
        for _ in range(fields_count):
            if pos + 4 > len(data):
                break
            field_len = int.from_bytes(data[pos:pos + 4], "little")
            pos += 4

            if field_len > 0:
                raw = data[pos:pos + field_len]
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1", errors="ignore")
            else:
                text = ""
            fields.append(sanitize_text(text))
            pos += field_len

            if pos % 4:
                pos += 4 - (pos % 4)

        if pos + 4 <= len(data):
            pos += 4

        if not filter_patterns or not any(
                p.match(key) for p in filter_patterns):
            records.append((key, fields))

    records.sort(key=lambda r: r[0])
    return records, LANGUAGES


def get_latest_apk_info() -> Tuple[str, str]:
    """
    Fetch BASE_URL, search for APK_REGEX. Return (version, download_link).
    Raises RuntimeError if not found.
    """
    logging.info(f"Fetching website: {BASE_URL}")
    try:
        resp = requests.get(BASE_URL, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Failed to fetch {BASE_URL}: {e}") from e

    match = APK_REGEX.search(resp.text)
    if not match:
        raise RuntimeError("Could not find Soul Knight APK link on page.")
    version = match.group(1)
    link = match.group(0)
    logging.info(f"Found version: {version}")
    return version, link


def ensure_apk_extracted(version: str, link: str) -> Path:
    """
    Download the APK if needed, then extract it into data/sk.
    Returns the path to the extracted folder (sk_extracted_path).
    """
    versioned_apk_file = DATA_DIR / f"sk-{version}.apk"
    sk_extracted_path = DATA_DIR / f"sk-{version}"

    if not versioned_apk_file.exists():
        download_file(link, versioned_apk_file)
    else:
        logging.info(f"APK already exists: {versioned_apk_file}")

    if not sk_extracted_path.exists():
        try:
            sk_extracted_path.mkdir(parents=True, exist_ok=False)
            with zipfile.ZipFile(versioned_apk_file, "r") as zf:
                zf.extractall(sk_extracted_path)
        except zipfile.BadZipFile as e:
            raise RuntimeError(
                f"Corrupted APK zip: {versioned_apk_file}") from e
        except Exception as e:
            raise RuntimeError(f"Failed extracting APK: {e}") from e
        logging.info(f"APK extracted to: {sk_extracted_path}")
    else:
        logging.info(f"APK already extracted at: {sk_extracted_path}")

    return sk_extracted_path


def ensure_asset_studio() -> Path:
    """
    Download AssetStudio CLI ZIP if needed, extract it under DATA_DIR/AssetStudio.
    Returns the path to the AssetStudio folder.
    """
    if not ASSET_STUDIO_ZIP.exists():
        download_file(ASSET_STUDIO_CLI_URL, ASSET_STUDIO_ZIP)
    else:
        logging.info(f"AssetStudio ZIP already present: {ASSET_STUDIO_ZIP}")

    if not ASSET_STUDIO_DIR.exists():
        extract_zip(ASSET_STUDIO_ZIP, ASSET_STUDIO_DIR)
    else:
        logging.info(f"AssetStudio already extracted at: {ASSET_STUDIO_DIR}")

    return ASSET_STUDIO_DIR


def run_asset_extractions(sk_extracted_path: Path) -> None:
    """
    1) Extract I2Languages .dat (monobehaviour/raw)
    2) Delete any small I2Languages*.dat (< 2 MB)
    3) Extract WeaponInfo (textasset/export)
    """
    unity_data = sk_extracted_path / "assets/bin/Data/data.unity3d"
    managed_folder = sk_extracted_path / "assets/bin/Data/Managed"

    if not unity_data.exists():
        raise FileNotFoundError(f"Unity data file missing: {unity_data}")
    if not managed_folder.exists() or not managed_folder.is_dir():
        raise FileNotFoundError(f"Managed folder missing: {managed_folder}")

    try:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise RuntimeError(
            f"Could not create export directory {EXPORT_DIR}: {e}") from e

    run_asset_studio_cli(
        ASSET_STUDIO_DIR,
        unity_data_path=unity_data,
        output_dir=EXPORT_DIR,
        asset_type="monobehaviour",
        mode="raw",
        filter_name="i2language",
        assembly_folder=managed_folder,
    )

    removed_any = False
    for dat_file in EXPORT_DIR.rglob("I2Languages*.dat"):
        try:
            size = dat_file.stat().st_size
        except OSError as e:
            logging.warning(f"Could not stat file {dat_file}: {e}")
            continue

        if size < 2_000_000:
            try:
                dat_file.unlink()
                logging.info(
                    f"Removed SMALL I2 file: {dat_file.name} ({size} bytes)")
                removed_any = True
            except Exception as e:
                logging.warning(f"Failed to remove {dat_file}: {e}")

    if not removed_any:
        logging.info("No SMALL I2Languages*.dat files were found to remove.")

    run_asset_studio_cli(
        ASSET_STUDIO_DIR,
        unity_data_path=unity_data,
        output_dir=EXPORT_DIR,
        asset_type="textasset",
        mode="export",
        filter_name="WeaponInfo",
    )


def find_valid_i2_dat() -> Path:
    """
    Find the first I2Languages*.dat in EXPORT_DIR with size ≥ 2 MB.
    Raises FileNotFoundError if none found.
    """
    for dat_file in EXPORT_DIR.rglob("I2Languages*.dat"):
        try:
            size = dat_file.stat().st_size
        except OSError:
            continue
        if size >= 2_000_000:
            logging.info(f"Found valid I2 dat: {dat_file.name} ({size} bytes)")
            return dat_file
    raise FileNotFoundError(
        "No valid (≥2 MB) I2Languages .dat file found under export/.")


def write_i2_csv(version: str, records: List[Tuple[str, List[str]]]) -> Path:
    """
    Given (key, [fields...]) records, write them into I2language_{version}.csv
    under the script folder. Returns the CSV path.
    """
    csv_path = SCRIPT_DIR / f"I2language_{version}.csv"
    logging.info(f"Writing CSV: {csv_path}")
    try:
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id"] + LANGUAGES)
            for key, fields in records:
                writer.writerow([key] + fields)
    except Exception as e:
        raise RuntimeError(f"Failed writing CSV {csv_path}: {e}") from e
    return csv_path


def load_language_map(csv_path: Path,
                      language: str = "English") -> Dict[str, str]:
    """
    Load the CSV and resolve aliases like `{boss18}` → boss18 → final English string.
    Returns: dict of ID → English string (fully resolved)
    """
    raw_map: Dict[str, str] = {}
    resolved_map: Dict[str, str] = {}

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rid = row["id"].strip()
            eng = row.get(language, "").strip()
            raw_map[rid] = eng

    def resolve(key: str, visited=None) -> str:
        if key in resolved_map:
            return resolved_map[key]
        if visited is None:
            visited = set()
        if key in visited:
            return f"[Cyclic alias: {key}]"
        visited.add(key)

        val = raw_map.get(key, "")
        if val.startswith("{") and val.endswith("}"):
            ref = val[1:-1]
            resolved = resolve(ref, visited)
            resolved_map[key] = resolved
            return resolved
        else:
            resolved_map[key] = val
            return val

    # Resolve everything
    for k in raw_map:
        resolve(k)

    return resolved_map


def build_dictionaries(csv_path: Path) -> Dict[str, Dict]:
    """
    Read resolved language map and build all lookup dictionaries.
    """
    lang_map = load_language_map(csv_path)
    weapons_map = {}
    buff_names = {}
    buff_infos = {}
    challenge_names = {}
    challenge_titles = {}
    challenge_descs = {}
    materials = {}
    plant_ids = {}
    pets = {}
    characters: Dict[str, Dict[str, str]] = {}

    for rid, eng in lang_map.items():
        if rid.startswith("weapon/"):
            weapons_map[rid.replace("weapon/", "")] = eng

        elif rid.startswith("Buff_name_"):
            buff_names[rid] = eng
        elif rid.startswith("Buff_info_"):
            buff_infos[rid] = eng

        elif rid.startswith("task/"):
            m = re.match(r"task/([^_]+)(_title|_desc)?", rid)
            if not m:
                continue
            cid, suffix = m.groups()
            if suffix == "_title":
                challenge_titles[cid] = eng
            elif suffix == "_desc":
                challenge_descs[cid] = eng
            else:
                challenge_names[cid] = eng

        elif rid.startswith("material_"):
            materials[rid] = eng

        elif rid.startswith("plant_") and "/" not in rid:
            plant_ids[rid] = eng

        elif (rid.startswith("Pet_name_") and not rid.endswith("_des")
              and not rid.endswith("_lock")):
            pets[rid] = eng

        else:
            m = re.match(r"Character(\d+)_name_skin(\d+)", rid)
            if m:
                char_index, skin_index = m.groups()
                characters.setdefault(char_index, {})[skin_index] = eng

    return {
        "weapons": weapons_map,
        "buff_names": buff_names,
        "buff_infos": buff_infos,
        "challenge_names": challenge_names,
        "challenge_titles": challenge_titles,
        "challenge_descs": challenge_descs,
        "materials": materials,
        "plants": plant_ids,
        "pets": pets,
        "characters": characters,
    }


def write_master_txt(
    version: str,
    weapon_json_path: Path,
    lang_maps: Dict[str, Dict],
) -> Path:
    """
    Read WeaponInfo.txt (JSON), sort weapons, then write out the big ASCII master file.
    Returns path to the TXT.
    """
    txt_path = SCRIPT_DIR / f"Allinfo_{version}.txt"
    logging.info(f"Writing master TXT: {txt_path}")
    if not weapon_json_path.exists():
        raise FileNotFoundError(
            f"WeaponInfo JSON not found: {weapon_json_path}")

    try:
        with open(weapon_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON in {weapon_json_path}: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Failed reading {weapon_json_path}: {e}") from e

    weapons = data.get("weapons", [])
    weapons_sorted = sorted(weapons, key=lambda w: w.get("name", ""))

    weapons_map = lang_maps["weapons"]
    buff_names = lang_maps["buff_names"]
    buff_infos = lang_maps["buff_infos"]
    challenge_names = lang_maps["challenge_names"]
    challenge_titles = lang_maps["challenge_titles"]
    challenge_descs = lang_maps["challenge_descs"]
    materials = lang_maps["materials"]
    plants = lang_maps["plants"]
    pets = lang_maps["pets"]
    characters = lang_maps["characters"]
    max_skin_ids = {}
    try:
        with open(txt_path, "w", encoding="utf-8") as out:

            out.write(
                "██     ██ ███████  █████  ██████   ██████  ███    ██\n"
                "██     ██ ██      ██   ██ ██   ██ ██    ██ ████   ██\n"
                "██  █  ██ █████   ███████ ██████  ██    ██ ██ ██  ██\n"
                "██ ███ ██ ██      ██   ██ ██      ██    ██ ██  ██ ██\n"
                " ███ ███  ███████ ██   ██ ██       ██████  ██   ████\n\n")
            for w in weapons_sorted:
                name_key = w.get("name", "")
                english_name = weapons_map.get(name_key, "[Name Not Found]")
                out.write(f"{name_key}\n")
                out.write(f"    Name      : {english_name}\n")
                out.write(f"    Forgeable : {w.get('forgeable', False)}\n")
                out.write(f"    Is melee  : {w.get('isMelle', False)}\n")
                out.write(f"    Rarity    : {w.get('level', '')}\n")
                out.write(f"    Type      : {w.get('type', '')}\n\n")

            out.write(
                " ██████ ██   ██  █████  ██████   █████   ██████ ████████ ███████ ██████\n"
                "██      ██   ██ ██   ██ ██   ██ ██   ██ ██         ██    ██      ██   ██\n"
                "██      ███████ ███████ ██████  ███████ ██         ██    █████   ██████\n"
                "██      ██   ██ ██   ██ ██   ██ ██   ██ ██         ██    ██      ██   ██\n"
                " ██████ ██   ██ ██   ██ ██   ██ ██   ██  ██████    ██    ███████ ██   ██\n\n"
            )
            for char_index in sorted(characters.keys()):
                skins = characters[char_index]
                default_name = skins.get("0", "[Unknown]")
                out.write(f"c{char_index} = {default_name}\n")
                max_skin_id = max(int(sid) for sid in skins.keys())
                max_skin_ids[f"c{char_index}"] = max_skin_id
                for skin_index in sorted(skins.keys(), key=lambda x: int(x)):
                    skin_name = skins[skin_index]
                    out.write(
                        f"    c{char_index}_skin{skin_index} = {skin_name}\n")
                out.write("\n")

            out.write("██████  ███████ ████████\n"
                      "██   ██ ██         ██   \n"
                      "██████  █████      ██   \n"
                      "██      ██         ██   \n"
                      "██      ███████    ██   \n\n")
            for pet_id, pet_name in sorted(pets.items(), key=lambda kv: kv[0]):
                out.write(f"{pet_id.removeprefix('Pet_name_')}\n")
                out.write(f"    Display name : {pet_name}\n\n")

            out.write("██████  ██    ██ ███████ ███████ \n"
                      "██   ██ ██    ██ ██      ██      \n"
                      "██████  ██    ██ █████   █████   \n"
                      "██   ██ ██    ██ ██      ██      \n"
                      "██████   ██████  ██      ██      \n\n")
            buff_ids = set()
            buff_ids.update(
                k.replace("Buff_name_", "") for k in buff_names.keys())
            buff_ids.update(
                k.replace("Buff_info_", "") for k in buff_infos.keys())
            for bid in sorted(buff_ids):
                name_key = f"Buff_name_{bid}"
                info_key = f"Buff_info_{bid}"
                bname = buff_names.get(name_key, "[Name Not Found]")
                binfo = buff_infos.get(info_key, "[Description Not Found]")
                out.write(f"{bid}\n")
                out.write(f"    Name        : {bname}\n")
                out.write(f"    Description : {binfo}\n\n")

            out.write(
                " ██████ ██   ██  █████  ██       █████  ███    ██  ██████  ███████ \n"
                "██      ██   ██ ██   ██ ██      ██   ██ ████   ██ ██       ██      \n"
                "██      ███████ ███████ ██      ███████ ██ ██  ██ ██   ███ █████   \n"
                "██      ██   ██ ██   ██ ██      ██   ██ ██  ██ ██ ██    ██ ██      \n"
                " ██████ ██   ██ ██   ██ ███████ ██   ██ ██   ████  ██████  ███████ \n\n"
            )
            challenge_ids = set()
            challenge_ids.update(challenge_names.keys())
            challenge_ids.update(challenge_titles.keys())
            challenge_ids.update(challenge_descs.keys())

            for cid in sorted(challenge_ids,
                              key=lambda x: int(x) if x.isdigit() else x):
                name = challenge_names.get(cid, "[Name Not Found]")
                title = challenge_titles.get(cid, "[Title Not Found]")
                desc = challenge_descs.get(cid, "[Description Not Found]")
                out.write(f"{cid.removeprefix('name/')}\n")
                out.write(f"    Name        : {name}\n")
                out.write(f"    Title       : {title}\n")
                out.write(f"    Description : {desc}\n\n")

            out.write(
                "███    ███  █████  ████████ ███████ ██████  ██  █████  ██      \n"
                "████  ████ ██   ██    ██    ██      ██   ██ ██ ██   ██ ██      \n"
                "██ ████ ██ ███████    ██    █████   ██████  ██ ███████ ██      \n"
                "██  ██  ██ ██   ██    ██    ██      ██   ██ ██ ██   ██ ██      \n"
                "██      ██ ██   ██    ██    ███████ ██   ██ ██ ██   ██ ███████ \n\n"
            )
            for mid, mname in sorted(materials.items(), key=lambda kv: kv[0]):
                out.write(f"{mid}\n")
                out.write(f"    Display name : {mname}\n\n")

            out.write("██████  ██       █████  ███    ██ ████████ \n"
                      "██   ██ ██      ██   ██ ████   ██    ██    \n"
                      "██████  ██      ███████ ██ ██  ██    ██    \n"
                      "██      ██      ██   ██ ██  ██ ██    ██    \n"
                      "██      ███████ ██   ██ ██   ████    ██    \n\n")
            for pid, pname in sorted(plants.items(), key=lambda kv: kv[0]):
                out.write(f"{pid}\n")
                out.write(f"    Display name : {pname}\n\n")
            skin_id_json_path = SCRIPT_DIR / "highest_skin_ids.json"
            with open(skin_id_json_path, "w", encoding="utf-8") as f:
                json.dump(max_skin_ids, f, indent=2, sort_keys=True)
            logging.info(f"Exported max skin IDs to {skin_id_json_path}")
    except Exception as e:
        raise RuntimeError(f"Failed writing master TXT {txt_path}: {e}") from e

    return txt_path


def export_filtered_weapons_from_info(
    weapon_info_path: Path,
    weapons_map: Dict[str, str],
    output_path: Path,
) -> None:
    """
    Export only the weapons listed in WeaponInfo.txt, filtered by exclusion patterns,
    and write them as {weapon_id: english_name} JSON.
    """
    # Read WeaponInfo JSON
    try:
        with open(weapon_info_path, "r", encoding="utf-8") as f:
            info_data = json.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed reading WeaponInfo.txt: {e}") from e

    # Get weapon IDs from WeaponInfo
    weapon_list = info_data.get("weapons", [])
    ids_from_info = {w.get("name", "") for w in weapon_list if "name" in w}

    # Define exclusion patterns
    exclude_patterns = [
        re.compile(r"^weapon_000.*xx\d*$"),
        re.compile(r"^weapon_init.*xx\d*$"),
        re.compile(r"^transform_weapon_.*"),
    ]

    # Filter based on both inclusion and exclusion
    filtered = {}
    for wid in ids_from_info:
        if any(p.match(wid) for p in exclude_patterns):
            continue
        english_name = weapons_map.get(wid)
        if english_name:
            filtered[wid] = english_name

    # Write to JSON
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(filtered,
                      f,
                      ensure_ascii=False,
                      indent=2,
                      sort_keys=True)
    except Exception as e:
        raise RuntimeError(f"Failed writing filtered weapons JSON: {e}") from e


def export_weapon_evo_data(lang_map: Dict[str, str],
                           output_path: Path) -> None:
    import re
    from collections import defaultdict

    skin_pattern = re.compile(r"^(weapon_\w+)_s_\d+$")
    upgrade_pattern = re.compile(r"^desc_evolution_(weapon_\w+)$")

    weapon_skin_map = defaultdict(list)
    upgradable_weapons = set()

    for key in lang_map:
        if "/" in key:
            continue  # Skip keys like weapon/weapon_000

        # Match weapon skins
        m_skin = skin_pattern.match(key)
        if m_skin:
            base_weapon = m_skin.group(1)
            weapon_skin_map[base_weapon].append(key)
            continue

        # Match upgradable weapons
        m_upgrade = upgrade_pattern.match(key)
        if m_upgrade:
            weapon_id = m_upgrade.group(1)
            upgradable_weapons.add(weapon_id)
            continue

    # Sort outputs
    weapon_skin_map = {k: sorted(v) for k, v in weapon_skin_map.items()}
    upgradable_weapon_list = sorted(upgradable_weapons)

    # Final structure
    weapon_evo_data = {
        "blindBoxOpenCount0": 0,
        "favorWeapons": [],
        "lastOpenMachineHistoryStr0": "",
        "weapons": {
            weapon: {
                "Name":
                weapon,
                "Level":
                1 if weapon in upgradable_weapon_list else 0,
                "CurrentSkinIndex":
                1 if (skins := weapon_skin_map.get(weapon)) else 0,
                "UnlockedSkins":
                skins or []
            }
            for weapon in weapon_skin_map.keys() | upgradable_weapons
        }
    }

    # Write JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(weapon_evo_data,
                  f,
                  indent=2,
                  ensure_ascii=False,
                  sort_keys=True)

    print(f"Exported weapon metadata to: {output_path}")


def export_needed_data_from_langmap(lang_map: Dict[str, str],
                                    output_dir: Path) -> None:

    result = {
        "skin": defaultdict(dict),  # c1: {c1_skin0: name, ...}
        "pet": {},  # p0: name
        "material": {},  # material_id: name
        "character_skill": {}  # Character1_skill_1_name: name
    }

    # Patterns
    skin_pattern = re.compile(r"Character(\d+)_name_skin(\d+)")
    pet_pattern = re.compile(r"Pet_name_(\d+)")
    material_pattern = re.compile(
        r'(^material_(?!.*(?:activity|book|skill|new|money|multi|desc)).*)'
    )
    skill_pattern = re.compile(r"(Character\d+_skill_\d+_name)")
    for key, value in lang_map.items():
        # Skins
        m_skin = skin_pattern.fullmatch(key)
        if m_skin:
            char_index, skin_index = m_skin.groups()
            result["skin"][f"c{char_index}"][
                f"c{char_index}_skin{skin_index}"] = value
            continue

        # Pets
        m_pet = pet_pattern.fullmatch(key)
        if m_pet:
            pid = m_pet.group(1)
            result["pet"][pid] = value
            continue

        # Materials
        m_mat = material_pattern.fullmatch(key)
        if m_mat:
            mid = m_mat.group(1)
            result["material"][mid] = value
            continue

        # Character Skills
        m_skill = skill_pattern.fullmatch(key)
        if m_skill:
            sid = m_skill.group(1)
            result["character_skill"][sid] = value
            continue

    # Convert defaultdict to dict for JSON
    result["skin"] = dict(result["skin"])

    # Write to JSON
    with open(output_dir, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, sort_keys=True)

    logging.info(f"Exported: {output_dir}")


def main():

    try:
        version, link = get_latest_apk_info()
    except Exception as e:
        logging.error(f"Failed to get APK info: {e}")
        sys.exit(1)

    try:
        sk_extracted = ensure_apk_extracted(version, link)
    except Exception as e:
        logging.error(f"Failed to download/extract APK: {e}")
        sys.exit(1)

    try:
        global ASSET_STUDIO_DIR
        ASSET_STUDIO_DIR = ensure_asset_studio()
    except Exception as e:
        logging.error(f"Failed to prepare AssetStudio CLI: {e}")
        sys.exit(1)

    try:
        run_asset_extractions(sk_extracted)
    except Exception as e:
        logging.error(f"AssetStudio extraction failed: {e}")
        sys.exit(1)

    try:
        i2_dat = find_valid_i2_dat()
        records, languages = parse_i2_asset_file(i2_dat)
    except Exception as e:
        logging.error(f"Failed to parse I2 .dat: {e}")
        sys.exit(1)

    try:
        csv_path = write_i2_csv(version, records)
    except Exception as e:
        logging.error(f"Failed writing CSV: {e}")
        sys.exit(1)

    weapon_json_file = None
    try:
        for f in EXPORT_DIR.iterdir():
            if f.name.lower().endswith("weaponinfo.txt"):
                weapon_json_file = f
                break
        if not weapon_json_file:
            raise FileNotFoundError("WeaponInfo.txt not found under export/")
    except Exception as e:
        logging.error(f"Error locating WeaponInfo.txt: {e}")
        sys.exit(1)

    try:
        lang_maps = build_dictionaries(csv_path)
    except Exception as e:
        logging.error(f"Failed building language dictionaries: {e}")
        sys.exit(1)

    try:
        out_txt = write_master_txt(version, weapon_json_file, lang_maps)
        logging.info(f"All info fully baked: {out_txt}")
    except Exception as e:
        logging.error(f"Failed baking all info file: {e}")
        sys.exit(1)

    filtered_json_path = SCRIPT_DIR / f"weapons_{version}.json"
    try:
        export_filtered_weapons_from_info(
            weapon_info_path=weapon_json_file,
            weapons_map=lang_maps["weapons"],
            output_path=filtered_json_path,
        )
        logging.info(f"Filtered weapon JSON written: {filtered_json_path}")
    except Exception as e:
        logging.error(f"Failed exporting filtered weapons JSON: {e}")
    weapon_skin_path = SCRIPT_DIR / f"weapon_skins_{version}.json"
    lang_map = load_language_map(csv_path)
    lang_map_cn = load_language_map(csv_path, "Chinese (Simplified)")
    try:
        export_weapon_evo_data(lang_map, weapon_skin_path)
        logging.info(f"Weapon evolution data baked : {weapon_skin_path}")
    except Exception as e:
        logging.error(f"Cannot export weapon skin: {e}")
    try:
        export_needed_data_from_langmap(
            lang_map, SCRIPT_DIR / f"needed_data_{version}.json")
        export_needed_data_from_langmap(
            lang_map_cn, SCRIPT_DIR / f"needed_data_cn_{version}.json")
        logging.info("Exported needed data for English and Chinese")
    except Exception as e:
        logging.warning(f"Can't export: {e}")
    try:
        if DATA_DIR.exists():
            shutil.rmtree(DATA_DIR)
            logging.info(f"Cleaned up data folder: {DATA_DIR}")
    except Exception as e:
        logging.warning(
            f"Could not remove data folder (maybe in use): {DATA_DIR}: {e}")

    logging.info("All done.")


if __name__ == "__main__":
    main()
