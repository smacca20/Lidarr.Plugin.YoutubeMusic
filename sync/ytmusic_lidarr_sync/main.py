#!/usr/bin/env python3
"""YouTube Music -> Lidarr sync CLI.

Examples
--------
Report only (default, safe):
    python -m ytmusic_lidarr_sync --limit 50

Add missing artists/albums (no search):
    python -m ytmusic_lidarr_sync --add --limit 50

Add and trigger AlbumSearch so Lidarr grabs FLACs:
    python -m ytmusic_lidarr_sync --search --limit 50

Use a specific playlist by id:
    python -m ytmusic_lidarr_sync --playlist PLabc123... --search
"""
from __future__ import annotations

import argparse
import json
import sys

from .auth import build_ytmusic, extract_tracks, oauth_login
from .config import load_config
from .lidarr_client import LidarrClient, LidarrError
from .syncer import SyncOptions, SyncResult, Syncer


def _playlist_id(value: str) -> str:
    """Extract a bare playlist ID from an ID or a music.youtube.com URL."""
    import urllib.parse

    value = (value or "").strip()
    if not value:
        return value
    if value.startswith("http"):
        parsed = urllib.parse.urlparse(value)
        query = urllib.parse.parse_qs(parsed.query)
        if "list" in query:
            return query["list"][0]
        return parsed.path.rstrip("/").rsplit("/", 1)[-1]
    return value


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="youtube-music-lidarr-sync",
        description="Sync YouTube Music likes/playlists into Lidarr as artists+albums.",
    )
    parser.add_argument("--config", default=None, help="Path to a config.ini file.")
    parser.add_argument(
        "--playlist",
        default=None,
        help="YouTube Music playlist ID or URL. If omitted, uses your liked songs.",
    )
    parser.add_argument(
        "--playlists",
        default=None,
        help="Comma-separated names of YOUR YouTube Music playlists to sync "
             "(resolved via your library). Takes precedence over --playlist.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Max number of items to read per playlist/liked list (0 = unlimited). Default: 200.",
    )

    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--add",
        action="store_true",
        help="Add any missing artists/albums to Lidarr (mutates Lidarr).",
    )
    action.add_argument(
        "--search",
        action="store_true",
        help="Add missing artists/albums AND trigger AlbumSearch to grab files.",
    )

    parser.add_argument(
        "--dump",
        default=None,
        help="Write a JSON report of the run to this path.",
    )
    parser.add_argument(
        "--oauth-login",
        action="store_true",
        help="Run the YouTube Music OAuth device flow (requires oauth_client_id/secret in config) "
             "and save an auto-refreshing token. Runs only the login; no sync.",
    )
    parser.add_argument(
        "--monitor-albums",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Whether newly added albums are monitored (defaults to the config/plugin value: on).",
    )
    parser.add_argument(
        "--monitored",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Whether newly added artists are monitored (defaults to the config/plugin value: on).",
    )
    parser.add_argument(
        "--quality-profile",
        type=str,
        default=None,
        help="Override the quality profile for added artists (a profile NAME like 'Lossless' "
             "or a numeric id). Blank/omitted = auto-detect.",
    )
    parser.add_argument(
        "--metadata-profile",
        type=str,
        default=None,
        help="Override the metadata profile for added artists (a profile NAME like 'Standard' "
             "or a numeric id). Blank/omitted = auto-detect.",
    )
    return parser.parse_args(argv)


def _fetch_named_playlists(ytmusic, names_csv: str, limit: int) -> list[dict]:
    """Resolve comma-separated playlist NAMES from your library and merge their tracks."""
    names = [n.strip() for n in (names_csv or "").split(",") if n.strip()]
    library = ytmusic.get_library_playlists(limit=1000) or []
    by_name = {}
    for p in library:
        title = (p.get("title") or "").strip()
        if title and p.get("id"):
            by_name[title.lower()] = p["id"]

    merged: list[dict] = []
    seen = set()
    for name in names:
        pid = by_name.get(name.lower())
        if not pid:
            print(f"[warn] playlist not found in your library: '{name}'", flush=True)
            continue
        key = str(pid)
        if key in seen:
            continue
        seen.add(key)
        playlist = ytmusic.get_playlist(pid, limit=limit)
        title = playlist.get("title") or name
        print(f"[sync] reading playlist '{title}' (limit={limit})", flush=True)
        merged.extend(extract_tracks(playlist.get("tracks", [])))
    return merged


def _fetch_tracks(ytmusic, playlist_id: str | None, playlists_csv: str | None, limit: int) -> list[dict]:
    """Pull items from YT Music (liked songs, a playlist, or named playlists) and normalize."""
    if playlists_csv and playlists_csv.strip():
        return _fetch_named_playlists(ytmusic, playlists_csv, limit)
    if playlist_id:
        playlist_id = _playlist_id(playlist_id)
        playlist = ytmusic.get_playlist(playlist_id, limit=limit)
        print(f"[sync] reading playlist '{playlist.get('title', playlist_id)}'", flush=True)
        return extract_tracks(playlist.get("tracks", []))
    else:
        liked = ytmusic.get_liked_songs(limit=limit)
        print("[sync] reading your liked songs", flush=True)
        return extract_tracks(liked.get("tracks", []))


def _apply_throttle(ytmusic, delay_sec: float) -> object:
    """Add a small per-call delay + retry/backoff to YT Music API calls.

    YouTube Music's internal API can throttle (429 / "too many requests") when hit
    repeatedly; a short delay between calls and exponential backoff on rate-limit
    errors keeps large playlists from erroring or slowing to a crawl.
    """
    import time

    if ytmusic is None:
        return ytmusic
    delay = max(0.0, float(delay_sec))
    for name in ("get_playlist", "get_liked_songs", "get_library_playlists", "get_saved_albums"):
        orig = getattr(ytmusic, name, None)
        if orig is None:
            continue

        def wrap(*args, _o=orig, **kwargs):  # noqa: BLE001
            time.sleep(delay)
            for attempt in range(4):
                try:
                    return _o(*args, **kwargs)
                except Exception as exc:
                    s = str(exc).lower()
                    retryable = any(
                        k in s for k in ("429", "rate", "too many", "quota", "blocked", "temporary")
                    )
                    if not retryable or attempt == 3:
                        raise
                    time.sleep(1.0 * (attempt + 1))

        setattr(ytmusic, name, wrap)
    return ytmusic


def _print_report(result: SyncResult) -> None:
    print("\n================ SYNC REPORT ================")
    print(f"Items seen:        {result.records_seen}")
    print(f"Artists existing:  {result.artists_existing}")
    print(
        "Artists added:     "
        f"{','.join(a['name'] for a in result.artists_added) or 'none'}"
    )
    for a in result.artists_added:
        print(f"   [{a.get('action', '?')}] {a.get('name', '')}")
    print(f"Albums matched:    {len(result.albums_matched)}")
    for m in result.albums_matched:
        print(f"   {m.get('artist')} - {m.get('album')}")
    if result.albums_missing:
        print(f"Albums not found:  {len(result.albums_missing)}")
        for m in result.albums_missing:
            print(f"   {m}")
    print(f"Album searches (queued/run): {result.album_searches_dispatched}")
    if result.unmatched:
        print(f"Unmatched tracks:  {len(result.unmatched)}")
        for u in result.unmatched:
            print(
                f"   {u.get('title', '?')} - {', '.join(u.get('artists') or [])}"
                f" ({u.get('reason')})"
            )
    print("=============================================")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    config = load_config(args.config)

    if args.oauth_login:
        try:
            oauth_login(config.ytmusic)
        except Exception as exc:  # noqa: BLE001
            print(f"[error] OAuth login failed: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.monitor_albums is not None:
        config.lidarr.monitor_albums = args.monitor_albums
    if args.monitored is not None:
        config.lidarr.monitored = args.monitored
    if args.quality_profile is not None:
        config.lidarr.quality_profile = args.quality_profile
    if args.metadata_profile is not None:
        config.lidarr.metadata_profile = args.metadata_profile

    try:
        ytmusic = _apply_throttle(build_ytmusic(config.ytmusic), config.ytmusic.request_delay_sec)
        client = LidarrClient(config.lidarr)
    except LidarrError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    try:
        records = _fetch_tracks(ytmusic, args.playlist, args.playlists, args.limit)
    except Exception as exc:  # noqa: BLE001 - surface a friendly message
        print(f"[error] reading YouTube Music failed: {exc}", file=sys.stderr)
        print(
            "If you tried your liked songs, make sure headers_file/auth is set "
            "in config.ini (see README).",
            file=sys.stderr,
        )
        return 1

    if not records:
        print("[sync] no playable tracks found. Nothing to do.")
        return 0

    options = SyncOptions(add_missing=args.add or args.search, search=args.search)
    syncer = Syncer(client, options)
    result = SyncResult()

    try:
        syncer.sync(records, result)
    except LidarrError as exc:
        print(f"\n[error] {exc}", file=sys.stderr)
        return 2

    _print_report(result)

    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as fh:
            json.dump(result.to_dict(), fh, indent=2, ensure_ascii=False)
        print(f"[sync] report written to {args.dump}")

    return 0


if __name__ == "__main__":
    sys.exit(main())