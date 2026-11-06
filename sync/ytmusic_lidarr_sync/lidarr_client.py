"""Minimal client for the Lidarr REST API (v1)."""
from __future__ import annotations

from typing import Any

import requests

from .config import LidarrConfig


class LidarrError(RuntimeError):
    pass


class LidarrClient:
    def __init__(self, config: LidarrConfig):
        if not config.url:
            raise LidarrError("Lidarr URL is not set in config.")
        if not config.api_key:
            raise LidarrError("Lidarr API key is not set in config.")

        self.url = config.url.rstrip("/")
        self.api_key = config.api_key
        self.root_folder = config.root_folder
        self._desired_quality = config.quality_profile
        self._desired_metadata = config.metadata_profile
        self.language_profile_id = config.language_profile_id
        self.album_folder = config.album_folder
        self.monitor_albums = config.monitor_albums
        self.monitored = config.monitored

        # caches for "0 = auto-detect" profile resolution
        self._resolved_quality: int | None = None
        self._resolved_metadata: int | None = None

        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-Api-Key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    # -- low-level ---------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            resp = self.session.request(method, self.url + path, timeout=60, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as exc:  # include response body in the error
            detail = ""
            try:
                detail = resp.text[:500]
            except Exception:  # noqa: BLE001
                pass
            raise LidarrError(
                f"Lidarr {method} {path} failed with {exc}. "
                f"Body: {detail}"
            ) from exc
        except requests.RequestException as exc:
            raise LidarrError(f"Could not reach Lidarr at {self.url}: {exc}") from exc

    def get(self, path: str, params: dict | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: dict | None = None) -> Any:
        return self._request("POST", path, json=json)

    def put(self, path: str, json: dict | None = None) -> Any:
        return self._request("PUT", path, json=json)

    # -- lookups -----------------------------------------------------------
    def get_artists(self) -> list[dict]:
        return self.get("/api/v1/artist")

    def artist_lookup(self, term: str) -> list[dict]:
        return self.get("/api/v1/artist/lookup", params={"term": term})

    def album_lookup(self, term: str) -> list[dict]:
        return self.get("/api/v1/album/lookup", params={"term": term})

    def get_albums(self, artist_id: int | None = None) -> list[dict]:
        params = {}
        if artist_id is not None:
            params["artistId"] = artist_id
        return self.get("/api/v1/album", params=params or None)

    # -- mutations ---------------------------------------------------------
    def add_artist(self, artist_obj: dict) -> dict:
        created = self.post("/api/v1/artist", json=artist_obj)
        return created if isinstance(created, dict) else {}

    def update_artist(self, artist_obj: dict) -> dict:
        artist_id = artist_obj.get("id")
        updated = self.put(f"/api/v1/artist/{artist_id}", json=artist_obj)
        return updated if isinstance(updated, dict) else {}

    def add_album(self, album_obj: dict) -> dict:
        created = self.post("/api/v1/album", json=album_obj)
        return created if isinstance(created, dict) else {}

    def command(self, name: str, **body: Any) -> Any:
        return self.post("/api/v1/command", json={"name": name, **body})

    def refresh_artist(self, artist_id: int) -> None:
        self.command("RefreshArtist", artistIds=[artist_id])

    def search_albums(self, album_ids: list[int]) -> None:
        if album_ids:
            self.command("AlbumSearch", albumIds=list(album_ids))

    def search_artists(self, artist_ids: list[int]) -> None:
        if artist_ids:
            self.command("ArtistSearch", artistIds=list(artist_ids))

    # -- profile resolution (by NAME or numeric id; blank = auto-detect) --
    def quality_profile(self) -> int:
        if self._resolved_quality is None:
            self._resolved_quality = self._resolve_profile(
                "/api/v1/qualityprofile", self._desired_quality, ("lossless", "flac", "hi-res", "hifi")
            )
        return self._resolved_quality

    def metadata_profile(self) -> int:
        if self._resolved_metadata is None:
            self._resolved_metadata = self._resolve_profile(
                "/api/v1/metadataprofile", self._desired_metadata, ("standard",)
            )
        return self._resolved_metadata

    def _resolve_profile(self, path: str, desired: str, auto_preferred: tuple[str, ...]) -> int:
        """Resolve a profile to its id by NAME (exact, then substring), or numeric id.
        Blank/auto picks a preferred name match, else the lowest id."""
        try:
            profiles = self.get(path) or []
            candidates = [p for p in profiles if p.get("id")]
            if not candidates:
                return 1
            desired = (str(desired) if desired is not None else "").strip()
            if not desired:
                return self._auto_pick(candidates, auto_preferred)
            if desired.isdigit():
                return int(desired)
            dn = desired.lower()
            for profile in candidates:
                if (profile.get("name") or "").strip().lower() == dn:
                    return int(profile["id"])
            for profile in candidates:
                nm = (profile.get("name") or "").lower()
                if dn in nm or nm in dn:
                    return int(profile["id"])
            # requested name not found -> fall back to auto
            return self._auto_pick(candidates, auto_preferred)
        except Exception:  # noqa: BLE001
            return 1

    def _auto_pick(self, candidates: list[dict], preferred: tuple[str, ...]) -> int:
        for want in preferred:
            for profile in candidates:
                if want.lower() in (profile.get("name") or "").lower():
                    return int(profile["id"])
        return int(min(candidates, key=lambda p: p["id"])["id"])

    # -- builders ----------------------------------------------------------
    def build_add_artist_payload(self, lookup_result: dict, search_missing: bool = False) -> dict:
        """Expand a /artist/lookup result into a POST /api/v1/artist body."""
        payload = dict(lookup_result)
        payload["rootFolderPath"] = self.root_folder
        payload["qualityProfileId"] = self.quality_profile()
        payload["metadataProfileId"] = self.metadata_profile()
        payload["languageProfileId"] = self.language_profile_id
        payload["albumFolder"] = self.album_folder
        payload["monitored"] = self.monitored
        # Only the albums/singles that actually matched a liked track are monitored
        # (done explicitly via monitor_album), never the whole discography by default.
        payload["addOptions"] = {
            "monitored": False,
            "searchForMissingAlbums": search_missing,
        }
        return payload

    def monitor_album(self, album_obj: dict) -> dict:
        """Explicitly mark one album/single as monitored."""
        album_id = album_obj.get("id")
        if not album_id:
            return album_obj
        body = dict(album_obj)
        body["monitored"] = True
        try:
            with_alias = self.put(f"/api/v1/album/{album_id}", json=body)
            return with_alias or body
        except LidarrError:  # don't let a single monitoring failure abort the run
            return body

    # -- helper lookups within a fetched artist ----------------------------
    def find_existing_artist(self, foreign_artist_id: str) -> dict | None:
        faid = (foreign_artist_id or "").lower()
        for artist in self.get_artists():
            if str(artist.get("foreignArtistId", "")).lower() == faid:
                return artist
        return None

    def find_album_in_artist(
        self, albums: list[dict], title: str, year=None
    ) -> dict | None:
        """Find an album by title among album resources.

        Uses edition-marker-stripping normalization so e.g. YT's "MTV Unplugged (Live)"
        matches Lidarr's "MTV Unplugged"; falls back to substring containment.

        ``year`` (optional, e.g. "1992") is used ONLY to break ties among same-titled
        candidates (prefer the edition whose year matches); it never accepts a release
        whose title or artist does not already match.
        """
        from .matcher import norm_album_title

        tn = norm_album_title(title)
        exact: list[dict] = []
        partial: list[dict] = []
        for al in albums:
            at = norm_album_title(al.get("title", ""))
            if not at:
                continue
            if at == tn:
                exact.append(al)
            elif tn in at or at in tn:
                partial.append(al)

        def _album_year(al: dict) -> str:
            rd = al.get("releaseDate") or al.get("year") or ""
            return str(rd)[:4]

        def _year_ok(al: dict) -> int:
            if not year:
                return 0
            return 0 if _album_year(al) == str(year)[:4] else 1

        def _prefer(candidates: list[dict]) -> dict | None:
            # Prefer real "Album" releases over EPs/singles; then (if a year is known)
            # the edition whose year matches; then monitored.
            def key(al: dict) -> tuple:
                is_album = al.get("albumType") == "Album"
                return (
                    0 if is_album else 1,
                    _year_ok(al),
                    0 if al.get("monitored") else 1,
                )

            if not candidates:
                return None
            return sorted(candidates, key=key)[0]

        return _prefer(exact) or _prefer(partial)