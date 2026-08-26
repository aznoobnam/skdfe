"""Encrypted configuration export processing."""

import csv
from collections import defaultdict
import io
import json
import logging
from pathlib import Path

from .assetstudio import find_exported_text_asset
from .config import ITEM_PREFIX_GROUPS, ProjectPaths, XOR_KEY


def xor_repeating(data: str, key: str = XOR_KEY.decode()) -> str:
    """XOR Unicode characters with a repeating key."""
    if not key:
        raise ValueError("XOR key cannot be empty")
    return "".join(
        chr(ord(value) ^ ord(key[index % len(key)]))
        for index, value in enumerate(data)
    )


def parse_csv_keys(text: str) -> list[str]:
    """Read unique Key values, excluding the second CSV type row."""
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
        type_row = next(reader)
    except StopIteration as error:
        raise ValueError("CSV must contain a header and type row") from error
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


def classify_item_key(key: str) -> tuple[str, str]:
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


def group_item_keys(keys: list[str]) -> dict[str, object]:
    """Group item keys, flattening types with only fallback keys."""
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
                group: sorted(group_keys) for group, group_keys in sorted(groups.items())
            }
    return result


def write_config_json(
    enemy_text: str, item_text: str, enemy_json: Path, item_json: Path
) -> None:
    """Convert decrypted config CSV text to JSON key indexes."""
    enemy_keys = parse_csv_keys(enemy_text)
    item_keys = parse_csv_keys(item_text)
    enemy_json.write_text(
        json.dumps(enemy_keys, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    item_json.write_text(
        json.dumps(group_item_keys(item_keys), indent=2, ensure_ascii=False, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def decrypt_config_exports(paths: ProjectPaths) -> None:
    """Decrypt config CSVs, retain CSV artifacts, and generate ID indexes."""
    decrypted = {}
    for asset_name, output_name in (
        ("enemies.csv", "enemies.decrypted.csv"),
        ("items.csv", "items.decrypted.csv"),
    ):
        export_path = find_exported_text_asset(
            paths.config_export_dir / Path(asset_name).stem, asset_name
        )
        text = xor_repeating(export_path.read_bytes().decode("utf-8"))
        (paths.root / output_name).write_bytes(text.encode("utf-8"))
        decrypted[asset_name] = text
        logging.info("Decrypted config CSV: %s", paths.root / output_name)
    enemy_json = paths.output("enemy.json")
    item_json = paths.output("item.json")
    write_config_json(decrypted["enemies.csv"], decrypted["items.csv"], enemy_json, item_json)
    logging.info("Generated %s and %s", enemy_json.name, item_json.name)
