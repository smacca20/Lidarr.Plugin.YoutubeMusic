"""Configuration loading/parsing."""
from __future__ import annotations

import configparser
import os
import re
from dataclasses import dataclass

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(PROJECT_DIR, "config.ini")


@dataclass
class LidarrConfig:
    url: str = "http://localhost:8686"
    api_key: str = ""
    root_folder: str = ""
    quality_profile_id: int = 1
    metadata_profile_id: int = 1
    language_profile_id: int = 1
    album_folder: bool = True
    monitor_albums: bool = True


@dataclass
class YTMusicConfig:
    # Path to a headers.json produced by `python -m ytmusicapi setup`
    headers_file: str = ""
    # Raw cookie / headers dict string accepted by YTMusic(auth=...)
    auth: str = ""
    # OAuth (durable, auto-refreshing) - created via `--oauth-login`
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_token_file: str = ""  # defaults to "oauth.json" in the cwd / project dir


@dataclass
class Config:
    lidarr: LidarrConfig
    ytmusic: YTMusicConfig
    path: str


def _parse_bool(value: str, default: bool = True) -> bool:
    value = (value or "").strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    return default


def _parse_int(value: str, default: int = 1) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


_APIKEY_RE = re.compile(r"<ApiKey>\s*([^<]+?)\s*</ApiKey>", re.IGNORECASE)


def _looks_local(url: str) -> bool:
    return "://localhost" in url or "://127." in url or url.startswith("localhost")


def _discover_api_key() -> str:
    """Read the Lidarr API key from its own config.xml (config on the same host)."""
    candidates = (
        "/config/config.xml",
        os.path.join(os.environ.get("PROGRAMDATA", ""), "Lidarr", "config.xml"),
        os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Lidarr", "config.xml"),
        os.path.join(os.path.expanduser("~"), ".config", "lidarr", "config.xml"),
    )
    for candidate in candidates:
        try:
            if os.path.exists(candidate):
                with open(candidate, encoding="utf-8") as fh:
                    match = _APIKEY_RE.search(fh.read())
                    if match:
                        return match.group(1)
        except OSError:
            continue
    return ""


def load_config(path: str | None = None) -> Config:
    """Load config from an INI file (or defaults if it does not exist)."""
    path = path or DEFAULT_CONFIG_PATH

    parser = configparser.ConfigParser()
    if os.path.exists(path):
        parser.read(path)
    else:
        parser.add_section("lidarr")
        parser.add_section("ytmusic")

    def _get(section: str, key: str, default: str = "") -> str:
        try:
            return parser.get(section, key) or default
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default

    lidarr = LidarrConfig()
    lidarr.url = _get("lidarr", "url", lidarr.url).strip().rstrip("/")
    lidarr.api_key = _get("lidarr", "api_key", "").strip()
    lidarr.root_folder = _get("lidarr", "root_folder", "").strip()
    lidarr.quality_profile_id = _parse_int(
        _get("lidarr", "quality_profile_id", ""), lidarr.quality_profile_id
    )
    lidarr.metadata_profile_id = _parse_int(
        _get("lidarr", "metadata_profile_id", ""), lidarr.metadata_profile_id
    )
    lidarr.language_profile_id = _parse_int(
        _get("lidarr", "language_profile_id", ""), lidarr.language_profile_id
    )
    lidarr.album_folder = _parse_bool(
        _get("lidarr", "album_folder", ""), lidarr.album_folder
    )
    lidarr.monitor_albums = _parse_bool(
        _get("lidarr", "monitor_albums", ""), lidarr.monitor_albums
    )

    # If no API key was provided and we're talking to a local Lidarr, auto-read it
    # from Lidarr's own config.xml so a base install only needs the auth cookie.
    if not lidarr.api_key and _looks_local(lidarr.url):
        lidarr.api_key = _discover_api_key()

    yt = YTMusicConfig()
    yt.headers_file = _get("ytmusic", "headers_file", "").strip()
    yt.auth = _get("ytmusic", "auth", "").strip()
    yt.oauth_client_id = _get("ytmusic", "oauth_client_id", "").strip()
    yt.oauth_client_secret = _get("ytmusic", "oauth_client_secret", "").strip()
    yt.oauth_token_file = _get("ytmusic", "oauth_token_file", "").strip()

    return Config(lidarr=lidarr, ytmusic=yt, path=path)