import re
import sys
import csv
import io
import json
import os
import time
import shutil
import logging
import zipfile
import requests
import subprocess
import tempfile
from pathlib import Path
from collections import defaultdict
from typing import List, Tuple, Dict

BASE_URL = "http://www.chillyroom.com/zh"
APK_REGEX = re.compile(
    r"https://pages.chillyroom.com/GameOfficialWebsite/strapi-cms/\w+_Soul_Knight_release_chillyroom_([_\d]+)_\w+\.apk"
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
CONFIG_EXPORT_DIR = DATA_DIR / "config_export"
CHARACTER_EXPORT_DIR = DATA_DIR / "character_export"
ASSET_STUDIO_ZIP = DATA_DIR / "AssetStudio.zip"
ASSET_STUDIO_DIR = DATA_DIR / "AssetStudio"
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
    filter_name: str = None,
    assembly_folder: Path = None,
    extra_args: List[str] = None,
) -> None:
    """
    Invoke AssetStudioModCLI with subprocess.
    - `asset_type`: e.g. "monobehaviour" or "textasset"
    - `mode`: e.g. "raw" or "export"
    - `filter_name`: e.g. "i2language" or "WeaponInfo"
    - `assembly_folder`: required only for monobehaviour extraction.
    - `extra_args`: additional trusted AssetStudio CLI arguments.
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
    ]
    if filter_name:
        cmd.extend(["--filter-by-name", filter_name])
    if assembly_folder:
        if not assembly_folder.exists() or not assembly_folder.is_dir():
            raise FileNotFoundError(
                f"Assembly folder not found: {assembly_folder}")
        cmd.extend(["--assembly-folder", str(assembly_folder)])
    if extra_args:
        cmd.extend(extra_args)

    logging.info("Running AssetStudioModCLI: " + " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, cwd=asset_studio_dir)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"AssetStudioModCLI failed (exit code {e.returncode})") from e
    logging.info(f"AssetStudio CLI finished extracting {asset_type}.")


def read_hero_character_ids(manifest_path: Path) -> List[int]:
    """Read and validate contiguous character IDs from hero.manifest."""
    pattern = re.compile(r"^- Assets/RGPrefab/Player/c(\d+)\.prefab$", re.I)
    ids = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        match = pattern.fullmatch(line.strip())
        if match:
            ids.append(int(match.group(1)))
    if not ids:
        raise ValueError(f"No character prefabs found in {manifest_path}")
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate character ID in {manifest_path}")
    ids.sort()
    if ids != list(range(ids[-1] + 1)):
        raise ValueError(f"Character IDs are not contiguous: {ids}")
    return ids


def read_character_names(dump_dir: Path, expected_ids: List[int]) -> List[str]:
    """Read CharacterSprites base-skin rows in numeric character-ID order."""
    matches = []
    for path in dump_dir.rglob("*.txt"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r'^\s*string m_Name = "CharacterSprites"', text, re.M):
            matches.append(text)
    if len(matches) != 1:
        raise ValueError(f"Expected one CharacterSprites dump; found {len(matches)}")

    model_pattern = re.compile(
        r"CharacterSpriteModel data\s+int characterIndex = (\d+)\s+"
        r"int skinIndex = (\d+)(.*?)(?=\n\s*(?:\[\d+\]\s*\n\s*)?"
        r"CharacterSpriteModel data|\Z)",
        re.S,
    )
    path_pattern = re.compile(
        r'string path = "Skin/Character/([^/]+)/Skin_(\d+)/', re.I)
    names = {}
    for character_id, skin_index, body in model_pattern.findall(matches[0]):
        if skin_index != "0":
            continue
        paths = {(name, path_skin_index)
                 for name, path_skin_index in path_pattern.findall(body)
                 if path_skin_index == "0"}
        if len(paths) != 1:
            raise ValueError(
                f"Character {character_id} base skin has {len(paths)} code names")
        name = paths.pop()[0]
        character_id = int(character_id)
        if character_id in names and names[character_id] != name:
            raise ValueError(f"Conflicting base names for character {character_id}")
        names[character_id] = name

    if sorted(names) != expected_ids:
        raise ValueError(
            f"CharacterSprites IDs do not match hero manifest: {sorted(names)}"
        )
    ordered = [names[character_id] for character_id in expected_ids]
    if len(ordered) != len(set(ordered)):
        raise ValueError("Character code names are not unique")
    return ordered


def write_json_atomic(output_path: Path, value: object) -> None:
    """Write formatted JSON without exposing a partial target file."""
    content = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", newline="\n", delete=False,
                dir=output_path.parent, prefix=f".{output_path.name}.") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.replace(temporary_name, output_path)
        temporary_name = None
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def generate_char_code_names(sk_extracted_path: Path) -> Path:
    """Extract and write char_code_name.json in numeric character-ID order."""
    bundle_root = sk_extracted_path / "assets/AssetBundles"
    common_bundle = bundle_root / "common.ab"
    hero_manifest = bundle_root / "hero.manifest"
    for path in (common_bundle, hero_manifest):
        if not path.is_file():
            raise FileNotFoundError(f"Character extraction input missing: {path}")

    character_ids = read_hero_character_ids(hero_manifest)
    if CHARACTER_EXPORT_DIR.exists():
        shutil.rmtree(CHARACTER_EXPORT_DIR)
    run_asset_studio_cli(
        ASSET_STUDIO_DIR,
        common_bundle,
        CHARACTER_EXPORT_DIR,
        "monobehaviour",
        "dump",
        filter_name="CharacterSprites",
        extra_args=["-g", "none", "-f", "pathID"],
    )
    names = read_character_names(CHARACTER_EXPORT_DIR, character_ids)
    output_path = SCRIPT_DIR / "char_code_name.json"
    write_json_atomic(output_path, names)
    logging.info(f"Generated character code names: {output_path}")
    return output_path


def xor_repeating(data: str, key: str = XOR_KEY.decode()) -> str:
    """XOR Unicode characters with a repeating key."""
    if not key:
        raise ValueError("XOR key cannot be empty")
    return "".join(
        chr(ord(value) ^ ord(key[index % len(key)]))
        for index, value in enumerate(data)
    )


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


def parse_csv_keys(text: str) -> List[str]:
    """Read unique Key values, excluding the second CSV type row."""
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
        type_row = next(reader)
    except StopIteration as e:
        raise ValueError("CSV must contain a header and type row") from e

    if "Key" not in header:
        raise ValueError("CSV header does not contain Key")
    if len(type_row) != len(header):
        raise ValueError("CSV type row does not match header width")

    key_index = header.index("Key")
    keys = []
    seen = set()
    for row_number, row in enumerate(reader, start=3):
        if not row or all(not field for field in row):
            continue
        if len(row) != len(header):
            raise ValueError(f"CSV row {row_number} does not match header width")
        key = row[key_index].strip()
        if not key:
            raise ValueError(f"CSV row {row_number} has an empty Key")
        if key in seen:
            raise ValueError(f"Duplicate Key: {key}")
        seen.add(key)
        keys.append(key)

    return sorted(keys)


def classify_item_key(key: str) -> Tuple[str, str]:
    """Map an item key to a predetermined prefix group."""
    if key.startswith(("desc_", "feature_")):
        return "others", "others"

    for prefix, item_type, group in ITEM_PREFIX_GROUPS:
        if key == prefix or key.startswith(f"{prefix}_"):
            return item_type, group

    item_type, separator, _ = key.partition("_")
    if not separator or not item_type:
        raise ValueError(f"Item Key has no type prefix: {key}")
    return item_type.lower(), "others"


def group_item_keys(keys: List[str]) -> Dict[str, object]:
    """Group item keys, flattening types that only use the fallback group."""
    grouped = defaultdict(lambda: defaultdict(list))
    for key in keys:
        item_type, group = classify_item_key(key)
        grouped[item_type][group].append(key)

    result = {}
    for item_type, groups in sorted(grouped.items()):
        if set(groups) == {"others"}:
            result[item_type] = sorted(groups["others"])
        else:
            result[item_type] = {
                group: sorted(group_keys)
                for group, group_keys in sorted(groups.items())
            }
    return result


def write_config_json(
    enemy_csv: Path,
    item_csv: Path,
    enemy_json: Path,
    item_json: Path,
) -> None:
    """Convert decrypted config CSV Key columns to JSON."""
    enemy_keys = parse_csv_keys(enemy_csv.read_text(encoding="utf-8-sig"))
    item_keys = parse_csv_keys(item_csv.read_text(encoding="utf-8-sig"))
    enemy_json.write_text(
        json.dumps(enemy_keys, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    item_json.write_text(
        json.dumps(
            group_item_keys(item_keys),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )


def decrypt_config_exports(version: str) -> None:
    """Decrypt config CSVs and generate versioned enemy/item JSON files."""
    outputs = {
        "enemies.csv": SCRIPT_DIR / "enemies.decrypted.csv",
        "items.csv": SCRIPT_DIR / "items.decrypted.csv",
    }
    for asset_name, output_path in outputs.items():
        export_path = find_exported_text_asset(
            CONFIG_EXPORT_DIR / Path(asset_name).stem,
            asset_name,
        )
        encrypted = export_path.read_bytes().decode("utf-8")
        decrypted = xor_repeating(encrypted)
        output_path.write_bytes(decrypted.encode("utf-8"))
        logging.info(f"Decrypted config CSV: {output_path}")

    enemy_json = SCRIPT_DIR / f"enemy_{version}.json"
    item_json = SCRIPT_DIR / f"item_{version}.json"
    write_config_json(
        outputs["enemies.csv"],
        outputs["items.csv"],
        enemy_json,
        item_json,
    )
    logging.info(f"Generated {enemy_json.name} and {item_json.name}")


def sanitize_text(text: str) -> str:
    """
    Replace CRLF / CR / LF with literal '\\n', strip null bytes and
    other non-printable control characters, then strip whitespace.
    """
    text = text.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()

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
    if len(data) < 60:
        raise ValueError(f"I2 .dat header is truncated: {file_path}")

    record_count = int.from_bytes(data[56:60], "little")
    records: List[Tuple[str, List[str]]] = []
    pos = 60

    def require(size: int, context: str) -> None:
        if pos + size > len(data):
            raise ValueError(f"I2 record {record_index + 1}: truncated {context}")

    def align(context: str) -> None:
        nonlocal pos
        padding = (-pos) % 4
        require(padding, context)
        pos += padding

    def read_u32(context: str) -> int:
        nonlocal pos
        require(4, context)
        value = int.from_bytes(data[pos:pos + 4], "little")
        pos += 4
        return value

    for record_index in range(record_count):
        align("key alignment")
        key_len = read_u32("key length")
        if key_len == 0:
            raise ValueError(f"I2 record {record_index + 1}: empty key")

        require(key_len, "key")
        key_bytes = data[pos:pos + key_len].replace(b"\x00", b"")
        key = key_bytes.decode("utf-8", errors="ignore").strip()
        pos += key_len
        if not key:
            raise ValueError(f"I2 record {record_index + 1}: empty key")

        align("term-type alignment")
        term_type = read_u32("term type")
        if term_type != 0:
            raise ValueError(
                f"I2 record {record_index + 1} ({key!r}): unsupported "
                f"term type {term_type}"
            )

        fields_count = read_u32("field count")
        if fields_count != len(LANGUAGES):
            raise ValueError(
                f"I2 record {record_index + 1} ({key!r}): expected "
                f"{len(LANGUAGES)} fields, found {fields_count}"
            )

        fields: List[str] = []
        for field_index in range(fields_count):
            field_len = read_u32(f"field {field_index + 1} length")
            require(field_len, f"field {field_index + 1}")
            raw = data[pos:pos + field_len].replace(b"\x00", b"")
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1", errors="ignore")
            fields.append(sanitize_text(text))
            pos += field_len
            align(f"field {field_index + 1} alignment")

        flags_count = read_u32("flags count")
        if flags_count != len(LANGUAGES):
            raise ValueError(
                f"I2 record {record_index + 1} ({key!r}): expected "
                f"{len(LANGUAGES)} flags, found {flags_count}"
            )
        require(flags_count, "flags")
        pos += flags_count
        align("flags alignment")

        trailing_count = read_u32("trailing array count")
        if trailing_count != 0:
            raise ValueError(
                f"I2 record {record_index + 1} ({key!r}): unsupported "
                f"trailing array count {trailing_count}"
            )

        if not filter_patterns or not any(
                pattern.match(key) for pattern in filter_patterns):
            records.append((key, fields))

    records.sort(key=lambda record: record[0])
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
    version = match.group(1).replace("_",".")
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
    1) Remove stale and extract I2Languages .dat (monobehaviour/raw)
    2) Delete any small I2Languages*.dat (< 2 MB)
    3) Extract WeaponInfo and encrypted config CSVs (textasset/export)
    """
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
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        for dat_file in EXPORT_DIR.rglob("I2Languages*.dat"):
            dat_file.unlink()
    except Exception as e:
        raise RuntimeError(
            f"Could not refresh I2 exports under {EXPORT_DIR}: {e}") from e

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

    for asset_name in ("enemies.csv", "items.csv"):
        output_dir = CONFIG_EXPORT_DIR / Path(asset_name).stem
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True)
        run_asset_studio_cli(
            ASSET_STUDIO_DIR,
            unity_data_path=config_bundle,
            output_dir=output_dir,
            asset_type="textasset",
            mode="export",
            filter_name=Path(asset_name).stem,
        )


def find_valid_i2_dat() -> Path:
    """Find the canonical or sole large I2Languages export."""
    candidates = []
    for dat_file in sorted(EXPORT_DIR.rglob("I2Languages*.dat")):
        try:
            if dat_file.stat().st_size >= 2_000_000:
                candidates.append(dat_file)
        except OSError:
            continue

    if not candidates:
        raise FileNotFoundError(
            "No valid (≥2 MB) I2Languages .dat file found under export/.")

    canonical = [path for path in candidates if path.name == "I2Languages.dat"]
    if len(canonical) == 1:
        selected = canonical[0]
    elif len(candidates) == 1:
        selected = candidates[0]
    else:
        paths = ", ".join(str(path) for path in candidates)
        raise RuntimeError(f"Ambiguous I2Languages exports: {paths}")

    logging.info(
        f"Found valid I2 dat: {selected.name} ({selected.stat().st_size} bytes)"
    )
    return selected


def write_i2_csv(version: str, records: List[Tuple[str, List[str]]]) -> Path:
    """
    Given (key, [fields...]) records, write them into I2language_{version}.csv
    under the script folder. Returns the CSV path.
    """
    csv_path = SCRIPT_DIR / f"I2language_{version}.csv"
    seen = set()
    for record_index, (key, fields) in enumerate(records, start=1):
        if not key:
            raise ValueError(f"I2 record {record_index} has an empty key")
        if key in seen:
            raise ValueError(f"I2 record {record_index}: duplicate key {key!r}")
        seen.add(key)
        if len(fields) != len(LANGUAGES):
            raise ValueError(
                f"I2 record {record_index} ({key!r}): expected "
                f"{len(LANGUAGES)} fields, found {len(fields)}"
            )

    logging.info(f"Writing CSV: {csv_path}")
    try:
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, escapechar="\\", quoting=csv.QUOTE_MINIMAL)
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

    logging.info(f"Exported weapon skins data to: {output_path}")


def export_needed_data_from_langmap(lang_map: Dict[str, str],
                                    output_dir: Path) -> None:

    result = {
        "skin": defaultdict(dict),  # c1: {c1_skin0: name, ...}
        "pet": {},  # p0: name
        "material": {},  # material_id: name
        "character_skill": {},  # Character1_skill_1_name: name
        "weapon_skin": {}
    }

    # Patterns
    skin_pattern = re.compile(r"Character(\d+)_name_skin(\d+)")
    pet_pattern = re.compile(r"Pet_name_(\d+)")
    material_pattern = re.compile(
        r'(^material_(?!.*(?:activity|book|skill|new|money|multi|desc)).*)'
    )
    skill_pattern = re.compile(r"(Character\d+_skill_\d+_name)")
    weapon_skin_pattern = re.compile(r"(weapon_\w+_s_\d+)")
    with open("test.lagmap.txt", "w", encoding="utf-8") as f:
        json.dump(lang_map, f, indent=2, ensure_ascii=False, sort_keys=True)
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

        # Weapon Skins
        m_w_skin = weapon_skin_pattern.fullmatch(key)
        if m_w_skin:
            wsid = m_w_skin.group(1)
            result["weapon_skin"][wsid] = value
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
        generate_char_code_names(sk_extracted)
    except Exception as e:
        logging.error(f"Character code generation failed: {e}")
        sys.exit(1)

    try:
        decrypt_config_exports(version)
    except Exception as e:
        logging.error(f"Config export failed: {e}")
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
            # shutil.rmtree(DATA_DIR)
            logging.info(f"Cleaned up data folder: {DATA_DIR}")
    except Exception as e:
        logging.warning(
            f"Could not remove data folder (maybe in use): {DATA_DIR}: {e}")

    logging.info("All done.")


if __name__ == "__main__":
    main()
