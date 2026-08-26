"""APK and external-tool acquisition."""

import logging
import zipfile
from pathlib import Path

import requests

from .config import APK_REGEX, ASSET_STUDIO_CLI_URL, BASE_URL, ProjectPaths


def download_file(url: str, dest: Path, chunk_size: int = 8192) -> None:
    """Download a URL to a local file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading: {url}")
    try:
        with requests.get(url, verify=False, stream=True, timeout=30) as resp:
            resp.raise_for_status()
            with dest.open("wb") as file:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if chunk:
                        file.write(chunk)
        print("\nDownload complete.")
    except Exception as error:
        raise RuntimeError(f"Failed to download {url}: {error}") from error


def extract_zip(zip_path: Path, target_dir: Path) -> None:
    """Extract a ZIP file to a target directory."""
    if not zip_path.exists():
        raise FileNotFoundError(f"Zip file not found: {zip_path}")
    logging.info("Extracting zip: %s → %s", zip_path, target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(target_dir)
    except zipfile.BadZipFile as error:
        raise RuntimeError(f"Bad zip file {zip_path}: {error}") from error
    logging.info("Extraction complete.")


def get_latest_apk_info() -> tuple[str, str]:
    """Return the latest APK version and URL from the official page."""
    logging.info("Fetching website: %s", BASE_URL)
    try:
        response = requests.get(BASE_URL, timeout=15)
        response.raise_for_status()
    except Exception as error:
        raise RuntimeError(f"Failed to fetch {BASE_URL}: {error}") from error

    match = APK_REGEX.search(response.text)
    if not match:
        raise RuntimeError("Could not find Soul Knight APK link on page.")
    version = match.group(1).replace("_", ".")
    link = match.group(0)
    logging.info("Found version: %s", version)
    return version, link


def ensure_apk_extracted(paths: ProjectPaths, version: str, link: str) -> Path:
    """Download and cache-extract the versioned APK."""
    apk_file = paths.apk_file(version)
    extracted_path = paths.apk_dir(version)
    if not apk_file.exists():
        download_file(link, apk_file)
    else:
        logging.info("APK already exists: %s", apk_file)

    if not extracted_path.exists():
        try:
            extracted_path.mkdir(parents=True, exist_ok=False)
            with zipfile.ZipFile(apk_file, "r") as archive:
                archive.extractall(extracted_path)
        except zipfile.BadZipFile as error:
            raise RuntimeError(f"Corrupted APK zip: {apk_file}") from error
        except Exception as error:
            raise RuntimeError(f"Failed extracting APK: {error}") from error
        logging.info("APK extracted to: %s", extracted_path)
    else:
        logging.info("APK already extracted at: %s", extracted_path)
    return extracted_path


def ensure_asset_studio(paths: ProjectPaths) -> Path:
    """Download and cache-extract AssetStudio CLI."""
    if not paths.asset_studio_zip.exists():
        download_file(ASSET_STUDIO_CLI_URL, paths.asset_studio_zip)
    else:
        logging.info("AssetStudio ZIP already present: %s", paths.asset_studio_zip)
    if not paths.asset_studio_dir.exists():
        extract_zip(paths.asset_studio_zip, paths.asset_studio_dir)
    else:
        logging.info("AssetStudio already extracted at: %s", paths.asset_studio_dir)
    return paths.asset_studio_dir
