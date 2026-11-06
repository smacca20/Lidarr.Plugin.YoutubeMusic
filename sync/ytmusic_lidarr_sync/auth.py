"""Build a YTMusic client, handling optional auth."""
from __future__ import annotations

import json
import os
from typing import Optional

from ytmusicapi import YTMusic

from .config import YTMusicConfig

# When set, this env var supplies a raw YouTube Music browser Cookie. The Lidarr
# plugin passes the pasted cookie this way (held in memory, never written to disk).
YTMLIDARR_AUTH_COOKIE = "YTMLIDARR_AUTH_COOKIE"


def headers_from_cookie(cookie: str) -> dict:
    """Wrap a raw browser ``Cookie`` header value into a ytmusicapi headers dict.

    ytmusicapi treats headers that carry a Cookie + an ``Authorization`` value
    containing ``SAPISIDHASH`` as "browser" auth: it recomputes the real
    SAPISIDHASH per request from the cookie. The pasted cookie must include the
    full browser cookie (i.e. it must contain ``__Secure-3PAPISID``).
    """
    return {
        "Cookie": cookie,
        "X-Goog-AuthUser": "0",
        "Origin": "https://music.youtube.com",
        "Authorization": "SAPISIDHASH 0 0",
    }


def build_oauth(cfg: YTMusicConfig, silent: bool = False) -> Optional[YTMusic]:
    """Build a YTMusic client from an OAuth refresh token (durable, auto-refreshing)."""
    token_path = os.path.join(cfg.oauth_token_file) if cfg.oauth_token_file else "oauth.json"
    if cfg.oauth_client_id and cfg.oauth_client_secret and os.path.exists(token_path):
        from ytmusicapi.auth.oauth import OAuthCredentials

        creds = OAuthCredentials(cfg.oauth_client_id, cfg.oauth_client_secret)
        if not silent:
            print("[ytmusic] authenticating with OAuth (auto-refreshing token)", flush=True)
        return YTMusic(auth=token_path, oauth_credentials=creds)
    return None


def oauth_login(cfg: YTMusicConfig) -> None:
    """Run the YouTube Music OAuth device flow and save an auto-refreshing token."""
    if not (cfg.oauth_client_id and cfg.oauth_client_secret):
        raise RuntimeError(
            "OAuth requires [ytmusic] oauth_client_id and oauth_client_secret in config.ini.\n"
            "Create a Google Cloud OAuth client (see README 'OAuth') and paste them in before "
            "running --oauth-login."
        )

    from ytmusicapi.auth.oauth import OAuthCredentials, RefreshingToken

    token_path = cfg.oauth_token_file or "oauth.json"
    creds = OAuthCredentials(cfg.oauth_client_id, cfg.oauth_client_secret)
    RefreshingToken.prompt_for_token(creds, open_browser=True, to_file=token_path)
    print(f"[oauth] saved auto-refreshing token to {token_path}")


def build_ytmusic(cfg: YTMusicConfig, silent: bool = False) -> YTMusic:
    """Construct a YTMusic(api) client.

    Auth sources, highest priority first:
      1. the YTMLIDARR_AUTH_COOKIE env var (raw cookie string, in memory only)
      2. config.[ytmusic].auth  -> headers.json path, a {"..."} headers JSON, or a raw Cookie string
      3. config.[ytmusic].headers_file -> path to headers.json

    Without auth you cannot access "liked songs", but you can still read public playlists.
    """
    oauth = build_oauth(cfg, silent)
    if oauth is not None:
        return oauth

    auth_source: Optional[object] = None

    env_cookie = os.environ.get(YTMLIDARR_AUTH_COOKIE, "").strip()
    if env_cookie:
        auth_source = headers_from_cookie(env_cookie)
    elif cfg.auth and cfg.auth.strip():
        auth = cfg.auth.strip()
        if auth.startswith("{"):
            try:
                auth_source = json.loads(auth)
            except json.JSONDecodeError:
                auth_source = headers_from_cookie(auth)
        elif os.path.exists(auth):
            auth_source = auth  # path to headers.json
        else:
            auth_source = headers_from_cookie(auth)  # raw cookie string
    elif cfg.headers_file and os.path.exists(cfg.headers_file):
        auth_source = cfg.headers_file  # path to headers.json

    if auth_source is not None and not silent:
        print("[ytmusic] authenticating with saved credentials", flush=True)
    elif auth_source is None and not silent:
        print(
            "[ytmusic] running WITHOUT auth - liked songs will not be available; "
            "only public playlists will work. See README to set up headers_file.",
            flush=True,
        )

    return YTMusic(auth=auth_source) if auth_source is not None else YTMusic()


def extract_tracks(yt_items) -> list[dict]:
    """Normalize ytmusicapi list items into simple records."""
    records: list[dict] = []
    for item in yt_items or []:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("videoId") or "(untitled)"
        video_type = item.get("videoType") or ""

        artists: list[str] = []
        for a in item.get("artists") or []:
            name = (a or {}).get("name") if isinstance(a, dict) else a
            if name and name not in artists:
                artists.append(name)

        album: Optional[str] = None
        alb = item.get("album")
        if isinstance(alb, dict):
            album = alb.get("name")
        elif isinstance(alb, str) and alb:
            album = alb

        # Skip radio/artist "videos" that carry no channel metadata and no artists
        if not artists:
            continue

        year = item.get("year")
        if isinstance(year, str):
            year = year.strip()
            year = year if year.isdigit() else None
        else:
            year = None

        records.append(
            {
                "title": title,
                "artists": artists,
                "album": album,
                "year": year,
                "videoId": item.get("videoId"),
                "videoType": video_type,
            }
        )
    return records