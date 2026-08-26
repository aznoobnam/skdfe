"""I2 localization asset parsing and map loading."""

import csv
import re
from pathlib import Path

from .config import LANGUAGES, ProjectPaths


I2Record = tuple[str, list[str]]


def sanitize_text(text: str) -> str:
    """Normalize export text without changing visible line-break semantics."""
    text = text.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()


def parse_i2_asset_file(
    file_path: Path, filter_patterns: list[re.Pattern[str]] | None = None
) -> tuple[list[I2Record], tuple[str, ...]]:
    """Parse the supported I2 Languages binary format."""
    if not file_path.exists():
        raise FileNotFoundError(f"I2 .dat file not found: {file_path}")
    data = file_path.read_bytes()
    if len(data) < 60:
        raise ValueError(f"I2 .dat header is truncated: {file_path}")
    record_count = int.from_bytes(data[56:60], "little")
    records: list[I2Record] = []
    position = 60

    def require(size: int, context: str) -> None:
        if position + size > len(data):
            raise ValueError(f"I2 record {record_index + 1}: truncated {context}")

    def align(context: str) -> None:
        nonlocal position
        padding = (-position) % 4
        require(padding, context)
        position += padding

    def read_u32(context: str) -> int:
        nonlocal position
        require(4, context)
        value = int.from_bytes(data[position:position + 4], "little")
        position += 4
        return value

    for record_index in range(record_count):
        align("key alignment")
        key_length = read_u32("key length")
        if key_length == 0:
            raise ValueError(f"I2 record {record_index + 1}: empty key")
        require(key_length, "key")
        key = data[position:position + key_length].replace(b"\x00", b"").decode(
            "utf-8", errors="ignore"
        ).strip()
        position += key_length
        if not key:
            raise ValueError(f"I2 record {record_index + 1}: empty key")
        align("term-type alignment")
        term_type = read_u32("term type")
        if term_type != 0:
            raise ValueError(
                f"I2 record {record_index + 1} ({key!r}): unsupported term type {term_type}"
            )
        fields_count = read_u32("field count")
        if fields_count != len(LANGUAGES):
            raise ValueError(
                f"I2 record {record_index + 1} ({key!r}): expected "
                f"{len(LANGUAGES)} fields, found {fields_count}"
            )
        fields = []
        for field_index in range(fields_count):
            field_length = read_u32(f"field {field_index + 1} length")
            require(field_length, f"field {field_index + 1}")
            raw = data[position:position + field_length].replace(b"\x00", b"")
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1", errors="ignore")
            fields.append(sanitize_text(text))
            position += field_length
            align(f"field {field_index + 1} alignment")
        flags_count = read_u32("flags count")
        if flags_count != len(LANGUAGES):
            raise ValueError(
                f"I2 record {record_index + 1} ({key!r}): expected "
                f"{len(LANGUAGES)} flags, found {flags_count}"
            )
        require(flags_count, "flags")
        position += flags_count
        align("flags alignment")
        trailing_count = read_u32("trailing array count")
        if trailing_count != 0:
            raise ValueError(
                f"I2 record {record_index + 1} ({key!r}): unsupported "
                f"trailing array count {trailing_count}"
            )
        if not filter_patterns or not any(pattern.match(key) for pattern in filter_patterns):
            records.append((key, fields))
    records.sort(key=lambda record: record[0])
    return records, LANGUAGES


def write_i2_csv(paths: ProjectPaths, records: list[I2Record]) -> Path:
    """Write validated localization records using the established CSV dialect."""
    csv_path = paths.output("I2language.csv")
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
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, escapechar="\\", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["id", *LANGUAGES])
        writer.writerows(([key, *fields] for key, fields in records))
    return csv_path


def load_language_maps(csv_path: Path, languages: tuple[str, ...]) -> dict[str, dict[str, str]]:
    """Load and resolve several localization columns in one CSV pass."""
    raw_maps = {language: {} for language in languages}
    with csv_path.open("r", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            key = row["id"].strip()
            for language in languages:
                raw_maps[language][key] = row.get(language, "").strip()

    def resolve_all(raw_map: dict[str, str]) -> dict[str, str]:
        resolved_map: dict[str, str] = {}

        def resolve(key: str, visited: set[str] | None = None) -> str:
            if key in resolved_map:
                return resolved_map[key]
            visited = set() if visited is None else visited
            if key in visited:
                return f"[Cyclic alias: {key}]"
            visited.add(key)
            value = raw_map.get(key, "")
            if value.startswith("{") and value.endswith("}"):
                value = resolve(value[1:-1], visited)
            resolved_map[key] = value
            return value

        for key in raw_map:
            resolve(key)
        return resolved_map

    return {language: resolve_all(raw_map) for language, raw_map in raw_maps.items()}
