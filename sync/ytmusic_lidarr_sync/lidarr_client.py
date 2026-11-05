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
        self.quality_profile_id = config.quality_profile_id
        self.metadata_profile_id = config.metadata_profile_id
        self.language_profile_id = config.language_profile_id
        self.album_folder = config.album_folder
        self.monitor_albums = config.monitor_albums

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

    # -- builders ----------------------------------------------------------
    def build_add_artist_payload(self, lookup_result: dict, search_missing: bool = False) -> dict:
        """Expand a /artist/lookup result into a POST /api/v1/artist body."""
        payload = dict(lookup_result)
        payload["rootFolderPath"] = self.root_folder
        payload["qualityProfileId"] = self.quality_profile_id
        payload["metadataProfileId"] = self.metadata_profile_id
        payload["languageProfileId"] = self.language_profile_id
        payload["albumFolder"] = self.album_folder
        payload["monitored"] = True
        payload["addOptions"] = {
            "monitored": self.monitor_albums,
            "searchForMissingAlbums": search_missing,
        }
        return payload

    # -- helper lookups within a fetched artist ----------------------------
    def find_existing_artist(self, foreign_artist_id: str) -> dict | None:
        faid = (foreign_artist_id or "").lower()
        for artist in self.get_artists():
            if str(artist.get("foreignArtistId", "")).lower() == faid:
                return artist
        return None

    def find_album_in_artist(self, albums: list[dict], title: str) -> dict | None:
        """Find an album by (normalized) title among a list of album resources."""
        from .matcher import norm

        tn = norm(title)
        exact: list[dict] = []
        partial: list[dict] = []
        for al in albums:
            at = norm(al.get("title", ""))
            if not at:
                continue
            if at == tn:
                exact.append(al)
            elif tn in at or at in tn:
                partial.append(al)

        def _prefer(candidates: list[dict]) -> dict | None:
            # Prefer real "Album" releases over EPs/singles, then monitored.
            def key(al: dict) -> tuple:
                is_album = al.get("albumType") == "Album"
                return (0 if is_album else 1, 0 if al.get("monitored") else 1)

            if not candidates:
                return None
            return sorted(candidates, key=key)[0]

        return _prefer(exact) or _prefer(partial)