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
    quality_profile: str = ""   # profile NAME (or numeric id); blank = auto (prefers Lossless)
    metadata_profile: str = ""  # profile NAME (or numeric id); blank = auto (prefers Standard)
    language_profile_id: int = 1
    album_folder: bool = True
    monitor_albums: bool = True
    monitored: bool = True


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
_PORT_RE = re.compile(r"<Port>\s*(\d+)\s*</Port>", re.IGNORECASE)
_URLBASE_RE = re.compile(r"<UrlBase>\s*([^<]*?)\s*</UrlBase>", re.IGNORECASE)


def _looks_local(url: str) -> bool:
    return "://localhost" in url or "://127." in url or url.startswith("localhost")


def _config_xml_candidates() -> tuple[str, ...]:
    return (
        "/config/config.xml",
        os.path.join(os.environ.get("PROGRAMDATA", ""), "Lidarr", "config.xml"),
        os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Lidarr", "config.xml"),
        os.path.join(os.path.expanduser("~"), ".config", "lidarr", "config.xml"),
    )


def _discover_lidarr() -> dict:
    """Read the API key, port and URL base from Lidarr's own config.xml (same host)."""
    for candidate in _config_xml_candidates():
        try:
            if os.path.exists(candidate):
                with open(candidate, encoding="utf-8") as fh:
                    txt = fh.read()
                api = _APIKEY_RE.search(txt)
                port = _PORT_RE.search(txt)
                base = _URLBASE_RE.search(txt)
                return {
                    "apikey": api.group(1) if api else "",
                    "port": int(port.group(1)) if port else None,
                    "urlbase": (base.group(1).strip().strip("/") if base else ""),
                }
        except (OSError, ValueError):
            continue
    return {}


def _set_port(url: str, port: int) -> str:
    m = re.match(r"^(https?://[^/:]+)(?::\d+)?(.*)$", url)
    return f"{m.group(1)}:{port}{m.group(2)}" if m else url


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
    # Profile can be a NAME (e.g. Lossless / Standard) or a legacy numeric id.
    _qname = _get("lidarr", "quality_profile", "").strip()
    _qid = _parse_int(_get("lidarr", "quality_profile_id", ""), 0)
    lidarr.quality_profile = _qname or (str(_qid) if _qid > 0 else "")

    _mname = _get("lidarr", "metadata_profile", "").strip()
    _mid = _parse_int(_get("lidarr", "metadata_profile_id", ""), 0)
    lidarr.metadata_profile = _mname or (str(_mid) if _mid > 0 else "")

    lidarr.language_profile_id = _parse_int(
        _get("lidarr", "language_profile_id", ""), lidarr.language_profile_id
    )
    lidarr.album_folder = _parse_bool(
        _get("lidarr", "album_folder", ""), lidarr.album_folder
    )
    lidarr.monitor_albums = _parse_bool(
        _get("lidarr", "monitor_albums", ""), lidarr.monitor_albums
    )
    lidarr.monitored = _parse_bool(
        _get("lidarr", "monitored", ""), lidarr.monitored
    )

    local = _looks_local(lidarr.url)
    discovered = _discover_lidarr() if local else {}

    # Auto-read the API key from Lidarr's config.xml so a base install only needs auth.
    if not lidarr.api_key and discovered.get("apikey"):
        lidarr.api_key = discovered["apikey"]

    # Auto-match Lidarr's real port / URL base when talking to localhost, so a custom
    # port needs no manual config. An explicit [lidarr] port always wins.
    if local:
        explicit_port = _parse_int(_get("lidarr", "port", ""), 0)
        port = explicit_port or discovered.get("port")
        if port:
            lidarr.url = _set_port(lidarr.url, int(port))
        urlbase = discovered.get("urlbase")
        if urlbase:
            lidarr.url = lidarr.url.rstrip("/") + "/" + urlbase.lstrip("/")
        lidarr.url = lidarr.url.rstrip("/")

    yt = YTMusicConfig()
    yt.headers_file = _get("ytmusic", "headers_file", "").strip()
    yt.auth = _get("ytmusic", "auth", "").strip()
    yt.oauth_client_id = _get("ytmusic", "oauth_client_id", "").strip()
    yt.oauth_client_secret = _get("ytmusic", "oauth_client_secret", "").strip()
    yt.oauth_token_file = _get("ytmusic", "oauth_token_file", "").strip()

    return Config(lidarr=lidarr, ytmusic=yt, path=path)