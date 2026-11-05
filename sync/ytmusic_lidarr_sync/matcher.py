"""Name normalization and fuzzy comparison used to match YT Music items
to Lidarr / MusicBrainz releases."""
from __future__ import annotations

import re
import unicodedata

from .lidarr_client import LidarrClient

# Strip "feat." / "ft." / "with ..." from artist strings before comparing so that
# "Drake feat. 21 Savage" and "Drake" can still match.
_FEATURE_RE = re.compile(
    r"\b(feat(?:uring)?|ft\.?|with|prod\.?\s+by)\b.*", re.IGNORECASE
)

# Tokens that appear on YT Music for live/lyric/deluxe editions but rarely on
# plain MusicBrainz releases; ignore them when matching album titles.
_EDIT_SUFFIX_RE = re.compile(
    r"\b(deluxe|remastered|remaster|live|explicit|clean|bonus\s+tracks?)\b",
    re.IGNORECASE,
)


def norm(value: str | None) -> str:
    """Normalize a name/title to a comparable form."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = _FEATURE_RE.sub("", value)
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def norm_album_title(value: str | None) -> str:
    """Normalize an album title, ignoring common edition markers."""
    cleaned = _EDIT_SUFFIX_RE.sub("", norm(value))
    return re.sub(r"\s+", " ", cleaned).strip()


def score(a: str | None, b: str | None) -> float:
    """Similarity in [0, 1]: 1.0 exact, 0.6 one-is-substring-of-other, else 0."""
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.6
    return 0.0


def resolve_artist(client: LidarrClient, artist_names: list[str]) -> dict | None:
    """Return the best /artist/lookup result matching one of the given names."""
    for name in artist_names:
        if not name:
            continue
        try:
            results = client.artist_lookup(name)
        except Exception:  # keep going even if one lookup fails
            continue
        # Pass 1: exact normalized match on artist name.
        for r in results:
            if norm(r.get("artistName", "")) == norm(name):
                return r
    # Pass 2: loose match (substring) as a fallback.
    for name in artist_names:
        if not name:
            continue
        try:
            results = client.artist_lookup(name)
        except Exception:
            continue
        for r in results:
            if score(r.get("artistName", ""), name) > 0.0:
                return r
    return None


def resolve_album_metadata(
    client: LidarrClient, artist_name: str, album_name: str
) -> dict | None:
    """Find an /album/lookup result whose title+artist match YT Music naming."""
    if not album_name:
        return None
    term = f"{album_name} {artist_name}"
    try:
        results = client.album_lookup(term)
    except Exception:
        return None

    best: dict | None = None
    best_total = 0.0
    for r in results:
        artist_info = r.get("artist")
        found_artist = ""
        if isinstance(artist_info, dict):
            found_artist = artist_info.get("artistName", "")
        elif isinstance(artist_info, str):
            found_artist = artist_info

        at = norm_album_title(r.get("title", ""))
        an = norm_album_title(album_name)
        artist_score = score(found_artist, artist_name)
        if at == an and artist_score >= 0.6:
            total = 1.0 + artist_score
        elif at and (at in an or an in at) and artist_score >= 0.6:
            total = 0.5 + artist_score
        else:
            continue
        if total > best_total:
            best, best_total = r, total
    return best