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


def compare_album(candidate: dict, album_name: str | None) -> float:
    """How well a candidate artist's discography matches the given album name."""
    if not album_name:
        return 0.0
    want = norm_album_title(album_name)
    for al in (candidate.get("albums") or []):
        at = norm_album_title(al.get("title", ""))
        if not at:
            continue
        if at == want:
            return 1.0
        if want in at or at in want:
            return 0.6
    return 0.0


def _pick_artist_candidate(
    exact_candidates: list[dict],
    album_name: str | None = None,
    track_title: str | None = None,
) -> dict | None:
    """Among same-named artists, prefer the one whose album/title corroborates."""
    if not exact_candidates:
        return None
    if len(exact_candidates) == 1 or not (album_name or track_title):
        return exact_candidates[0]

    best = exact_candidates[0]
    best_score = -1.0
    for candidate in exact_candidates:
        sc = compare_album(candidate, album_name)
        if sc <= 0.0 and track_title:
            # If we have no album, use the track title to disambiguate.
            want = norm(track_title)
            for al in (candidate.get("albums") or []):
                at = norm(al.get("title", ""))
                if at and (at == want or want in at or at in want):
                    sc = max(sc, 0.5)
        if sc > best_score:
            best, best_score = candidate, sc
    return best


def resolve_artist(
    client: LidarrClient,
    artist_names: list[str],
    album_name: str | None = None,
    track_title: str | None = None,
) -> dict | None:
    """Return the best /artist/lookup result for one of the given names.

    Requires an EXACT normalized artist-name match (no fuzzy fallback, so a near-match
    like 'Stefen Hauk' does NOT get pinned onto 'Stefan'). Same-named artists are then
    disambiguated by album / track title. Returns None when there is no confident match.
    """
    for name in artist_names:
        if not name:
            continue
        try:
            results = client.artist_lookup(name)
        except Exception:  # keep going even if one lookup fails
            continue
        # Only confident matches: normalized name is identical.
        exact = [r for r in results if norm(r.get("artistName", "")) == norm(name)]
        if not exact:
            continue  # no confident match for this artist token; try the next
        return _pick_artist_candidate(exact, album_name, track_title)
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