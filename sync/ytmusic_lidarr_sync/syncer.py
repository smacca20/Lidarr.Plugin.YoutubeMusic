"""High-level sync flow: YT Music records -> Lidarr artists/albums."""
from __future__ import annotations

from dataclasses import dataclass, field

from .lidarr_client import LidarrClient, LidarrError
from .matcher import norm_album_title, resolve_album_metadata, resolve_artist


@dataclass
class SyncOptions:
    add_missing: bool = False      # create artists/albums in Lidarr
    search: bool = False           # trigger AlbumSearch in Lidarr


@dataclass
class SyncResult:
    records_seen: int = 0
    artists_added: list[dict] = field(default_factory=list)
    artists_existing: int = 0
    albums_matched: list[dict] = field(default_factory=list)
    albums_missing: list[str] = field(default_factory=list)
    album_searches_dispatched: int = 0
    unmatched: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "records_seen": self.records_seen,
            "artists_added": self.artists_added,
            "artists_existing": self.artists_existing,
            "albums_matched": self.albums_matched,
            "albums_missing": self.albums_missing,
            "album_searches_dispatched": self.album_searches_dispatched,
            "unmatched": self.unmatched,
        }


class Syncer:
    def __init__(self, client: LidarrClient, options: SyncOptions):
        self.client = client
        self.options = options
        self._artist_cache: dict[str, dict] = {}
        self._added_artist_ids: set[str] = set()
        self._album_ids_for_search: set[int] = set()
        self._monitored_album_ids: set[int] = set()

    def _get_artist_cached(self, foreign_artist_id: str) -> dict | None:
        key = (foreign_artist_id or "").lower()
        if key in self._artist_cache:
            return self._artist_cache[key]
        existing = self.client.find_existing_artist(foreign_artist_id)
        self._artist_cache[key] = existing if existing else None
        return existing

    def _ensure_artist(self, lookup_result: dict, result: SyncResult) -> dict:
        faid = str(lookup_result.get("foreignArtistId", ""))
        existing = self._get_artist_cached(faid)
        if existing:
            result.artists_existing += 1
            return existing

        if faid.lower() in self._added_artist_ids:
            for a in self.client.get_artists():
                if str(a.get("foreignArtistId", "")).lower() == faid.lower():
                    self._artist_cache[faid.lower()] = a
                    return a

        if not self.options.add_missing:
            result.artists_added.append(
                {"name": lookup_result.get("artistName", faid), "action": "WOULD_ADD"}
            )
            return lookup_result

        payload = self.client.build_add_artist_payload(
            lookup_result, search_missing=False
        )
        created = self.client.add_artist(payload)
        self._added_artist_ids.add(faid.lower())
        self._artist_cache[faid.lower()] = created
        result.artists_added.append(
            {
                "name": created.get("artistName") or lookup_result.get("artistName"),
                "id": created.get("id"),
                "action": "ADDED",
            }
        )
        return created

    # -- run ---------------------------------------------------------------
    def sync(self, records: list[dict], result: SyncResult) -> SyncResult:
        result.records_seen = len(records)

        for rec in records:
            title = rec.get("title", "")
            artist_names = rec.get("artists") or []
            album_name = rec.get("album")

            try:
                artist_lookup = resolve_artist(
                    self.client,
                    artist_names,
                    album_name=rec.get("album"),
                    track_title=rec.get("title"),
                )
            except LidarrError:
                raise

            if not artist_lookup:
                result.unmatched.append(
                    {
                        "title": title,
                        "artists": artist_names,
                        "album": album_name,
                        "reason": "no artist found in Lidarr/MusicBrainz",
                    }
                )
                continue

            artist_obj = self._ensure_artist(artist_lookup, result)

            if album_name:
                matched = self._match_album(artist_obj, rec)
                if matched is not None:
                    result.albums_matched.append(
                        {
                            "artist": artist_obj.get("artistName"),
                            "album": matched.get("title") or album_name,
                        }
                    )
                else:
                    # The artist is already added, and Lidarr imports its full
                    # discography (including this album), so this is not an unmatched
                    # track - just note it for review.
                    result.albums_missing.append(
                        f"{artist_obj.get('artistName') or ', '.join(artist_names)}"
                        f" - {album_name}"
                    )
            else:
                result.albums_matched.append(
                    {
                        "artist": artist_obj.get("artistName"),
                        "album": "(artist added; album unknown from YT Music)",
                    }
                )

        if self.options.search and self._album_ids_for_search:
            self.client.search_albums(list(self._album_ids_for_search))
            result.album_searches_dispatched = len(self._album_ids_for_search)

        return result

    def _match_album(self, artist_obj: dict, rec: dict) -> dict | None:
        album_name = rec.get("album")
        artist_id = artist_obj.get("id")
        albums = self.client.get_albums(artist_id) if artist_id else []

        matched = self.client.find_album_in_artist(albums, album_name)
        if matched is None and artist_id and self.options.add_missing:
            # Artist may have just been added; ask Lidarr to refresh so its
            # discography (and album IDs) are imported, then re-scan. Never run
            # in dry-run mode (that would mutate Lidarr).
            self.client.refresh_artist(artist_id)
            albums = self.client.get_albums(artist_id)
            matched = self.client.find_album_in_artist(albums, album_name)

        if matched is None:
            # Fallback: resolve the release via the album-lookup endpoint and
            # prefer an existing Lidarr album for that artist if present.
            first_artist = rec["artists"][0] if rec["artists"] else ""
            # Search by the edition-stripped title (e.g. "MTV Unplugged Live" -> "MTV
            # Unplugged") so Lidarr's /album/lookup is more likely to locate the base
            # release even when it lives under a differently-keyed artist entry.
            meta = resolve_album_metadata(self.client, first_artist, norm_album_title(album_name))
            if meta is None:
                return None
            meta_artist = meta.get("artist", {})
            meta_artist_id = meta_artist.get("id") if isinstance(meta_artist, dict) else None
            local = self.client.find_album_in_artist(
                self.client.get_albums(meta_artist_id),
                meta.get("title", album_name),
            )
            matched = local or meta if local else meta

        if matched is not None and matched.get("id"):
            album_id = int(matched["id"])
            # Monitor only this matched album/single (never the whole discography),
            # and only when we're actually mutating Lidarr (not a dry run).
            if self.options.add_missing and self.client.monitor_albums and album_id not in self._monitored_album_ids:
                self.client.monitor_album(matched)
                self._monitored_album_ids.add(album_id)
            if self.options.search:
                self._album_ids_for_search.add(album_id)

        return matched