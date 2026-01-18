"""MusicBrainz integration for metadata retrieval."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING

try:
    import musicbrainzngs
    HAS_MUSICBRAINZ = True
except ImportError:
    HAS_MUSICBRAINZ = False

if TYPE_CHECKING:
    from typing import Any


# Rate limiting: MusicBrainz requires max 1 request per second
_last_request_time: float = 0.0
RATE_LIMIT_SECONDS: float = 1.0


@dataclass
class ArtistInfo:
    """Information about an artist from MusicBrainz.

    Attributes:
        mbid: MusicBrainz artist ID.
        name: Artist name.
        sort_name: Name for sorting.
        type: Artist type (person, group, etc.).
        country: Country of origin.
        tags: Genre/style tags.
        disambiguation: Disambiguation comment.
    """

    mbid: str
    name: str
    sort_name: str = ""
    type: str = ""
    country: str = ""
    tags: list[str] = field(default_factory=list)
    disambiguation: str = ""


@dataclass
class ReleaseInfo:
    """Information about a release from MusicBrainz.

    Attributes:
        mbid: MusicBrainz release ID.
        title: Release title.
        artist: Primary artist name.
        date: Release date.
        country: Release country.
        status: Release status (official, etc.).
        label: Record label.
        catalog_number: Label catalog number.
        barcode: UPC/EAN barcode.
        tags: Genre/style tags.
    """

    mbid: str
    title: str
    artist: str = ""
    date: str = ""
    country: str = ""
    status: str = ""
    label: str = ""
    catalog_number: str = ""
    barcode: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class RecordingInfo:
    """Information about a recording from MusicBrainz.

    Attributes:
        mbid: MusicBrainz recording ID.
        title: Recording title.
        artist: Primary artist name.
        length_ms: Length in milliseconds.
        releases: Associated releases.
        tags: Genre/style tags.
        isrcs: International Standard Recording Codes.
    """

    mbid: str
    title: str
    artist: str = ""
    length_ms: int = 0
    releases: list[ReleaseInfo] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    isrcs: list[str] = field(default_factory=list)


@dataclass
class MusicBrainzResult:
    """Result from a MusicBrainz search.

    Attributes:
        recordings: Matched recordings.
        artists: Matched artists.
        releases: Matched releases.
        confidence: Overall confidence score (0-1).
    """

    recordings: list[RecordingInfo] = field(default_factory=list)
    artists: list[ArtistInfo] = field(default_factory=list)
    releases: list[ReleaseInfo] = field(default_factory=list)
    confidence: float = 0.0


def _ensure_musicbrainz() -> None:
    """Ensure musicbrainzngs is available and configured."""
    if not HAS_MUSICBRAINZ:
        raise ImportError(
            "musicbrainzngs is required for MusicBrainz integration. "
            "Install with: pip install musicbrainzngs"
        )

    # Set user agent (required by MusicBrainz)
    musicbrainzngs.set_useragent(
        "midi-analyzer",
        "0.1.0",
        "https://github.com/midi-analyzer/midi-analyzer",
    )


def _rate_limit() -> None:
    """Enforce rate limiting for MusicBrainz API."""
    global _last_request_time

    current_time = time.time()
    elapsed = current_time - _last_request_time

    if elapsed < RATE_LIMIT_SECONDS:
        time.sleep(RATE_LIMIT_SECONDS - elapsed)

    _last_request_time = time.time()


def _extract_tags(entity: dict[str, Any]) -> list[str]:
    """Extract tags from a MusicBrainz entity.

    Args:
        entity: MusicBrainz entity dictionary.

    Returns:
        List of tag names.
    """
    tags = []
    tag_list = entity.get("tag-list", [])
    for tag in tag_list:
        name = tag.get("name", "")
        if name:
            tags.append(name)
    return tags


def _parse_artist(artist_data: dict[str, Any]) -> ArtistInfo:
    """Parse artist data from MusicBrainz.

    Args:
        artist_data: Raw MusicBrainz artist data.

    Returns:
        Parsed ArtistInfo.
    """
    return ArtistInfo(
        mbid=artist_data.get("id", ""),
        name=artist_data.get("name", ""),
        sort_name=artist_data.get("sort-name", ""),
        type=artist_data.get("type", ""),
        country=artist_data.get("country", ""),
        tags=_extract_tags(artist_data),
        disambiguation=artist_data.get("disambiguation", ""),
    )


def _parse_release(release_data: dict[str, Any]) -> ReleaseInfo:
    """Parse release data from MusicBrainz.

    Args:
        release_data: Raw MusicBrainz release data.

    Returns:
        Parsed ReleaseInfo.
    """
    # Get artist from artist-credit
    artist = ""
    artist_credit = release_data.get("artist-credit", [])
    if artist_credit:
        first_credit = artist_credit[0]
        if isinstance(first_credit, dict):
            artist_info = first_credit.get("artist", {})
            artist = artist_info.get("name", "")

    # Get label info
    label = ""
    catalog_number = ""
    label_info = release_data.get("label-info-list", [])
    if label_info:
        first_label = label_info[0]
        label_entity = first_label.get("label", {})
        label = label_entity.get("name", "")
        catalog_number = first_label.get("catalog-number", "")

    return ReleaseInfo(
        mbid=release_data.get("id", ""),
        title=release_data.get("title", ""),
        artist=artist,
        date=release_data.get("date", ""),
        country=release_data.get("country", ""),
        status=release_data.get("status", ""),
        label=label,
        catalog_number=catalog_number,
        barcode=release_data.get("barcode", ""),
        tags=_extract_tags(release_data),
    )


def _parse_recording(recording_data: dict[str, Any]) -> RecordingInfo:
    """Parse recording data from MusicBrainz.

    Args:
        recording_data: Raw MusicBrainz recording data.

    Returns:
        Parsed RecordingInfo.
    """
    # Get artist from artist-credit
    artist = ""
    artist_credit = recording_data.get("artist-credit", [])
    if artist_credit:
        first_credit = artist_credit[0]
        if isinstance(first_credit, dict):
            artist_info = first_credit.get("artist", {})
            artist = artist_info.get("name", "")

    # Parse releases
    releases = []
    release_list = recording_data.get("release-list", [])
    for release in release_list:
        releases.append(_parse_release(release))

    # Get ISRCs
    isrcs = recording_data.get("isrc-list", [])

    return RecordingInfo(
        mbid=recording_data.get("id", ""),
        title=recording_data.get("title", ""),
        artist=artist,
        length_ms=recording_data.get("length", 0) or 0,
        releases=releases,
        tags=_extract_tags(recording_data),
        isrcs=isrcs,
    )


def search_recording(
    title: str,
    artist: str | None = None,
    limit: int = 5,
) -> list[RecordingInfo]:
    """Search for recordings by title and optional artist.

    Args:
        title: Recording title to search for.
        artist: Optional artist name to filter results.
        limit: Maximum number of results.

    Returns:
        List of matching recordings.
    """
    _ensure_musicbrainz()
    _rate_limit()

    # Build query
    query = f'recording:"{title}"'
    if artist:
        query += f' AND artist:"{artist}"'

    try:
        result = musicbrainzngs.search_recordings(
            query=query,
            limit=limit,
        )
    except musicbrainzngs.WebServiceError:
        return []

    recordings = []
    recording_list = result.get("recording-list", [])
    for recording in recording_list:
        recordings.append(_parse_recording(recording))

    return recordings


def search_artist(
    name: str,
    limit: int = 5,
) -> list[ArtistInfo]:
    """Search for artists by name.

    Args:
        name: Artist name to search for.
        limit: Maximum number of results.

    Returns:
        List of matching artists.
    """
    _ensure_musicbrainz()
    _rate_limit()

    try:
        result = musicbrainzngs.search_artists(artist=name, limit=limit)
    except musicbrainzngs.WebServiceError:
        return []

    artists = []
    artist_list = result.get("artist-list", [])
    for artist in artist_list:
        artists.append(_parse_artist(artist))

    return artists


def search_release(
    title: str,
    artist: str | None = None,
    limit: int = 5,
) -> list[ReleaseInfo]:
    """Search for releases by title and optional artist.

    Args:
        title: Release title to search for.
        artist: Optional artist name to filter results.
        limit: Maximum number of results.

    Returns:
        List of matching releases.
    """
    _ensure_musicbrainz()
    _rate_limit()

    # Build query
    query = f'release:"{title}"'
    if artist:
        query += f' AND artist:"{artist}"'

    try:
        result = musicbrainzngs.search_releases(query=query, limit=limit)
    except musicbrainzngs.WebServiceError:
        return []

    releases = []
    release_list = result.get("release-list", [])
    for release in release_list:
        releases.append(_parse_release(release))

    return releases


def get_recording_by_mbid(mbid: str) -> RecordingInfo | None:
    """Get recording details by MusicBrainz ID.

    Args:
        mbid: MusicBrainz recording ID.

    Returns:
        Recording info or None if not found.
    """
    _ensure_musicbrainz()
    _rate_limit()

    try:
        result = musicbrainzngs.get_recording_by_id(
            mbid,
            includes=["artists", "releases", "tags", "isrcs"],
        )
    except musicbrainzngs.WebServiceError:
        return None

    recording = result.get("recording", {})
    return _parse_recording(recording)


def get_artist_by_mbid(mbid: str) -> ArtistInfo | None:
    """Get artist details by MusicBrainz ID.

    Args:
        mbid: MusicBrainz artist ID.

    Returns:
        Artist info or None if not found.
    """
    _ensure_musicbrainz()
    _rate_limit()

    try:
        result = musicbrainzngs.get_artist_by_id(mbid, includes=["tags"])
    except musicbrainzngs.WebServiceError:
        return None

    artist = result.get("artist", {})
    return _parse_artist(artist)


def get_release_by_mbid(mbid: str) -> ReleaseInfo | None:
    """Get release details by MusicBrainz ID.

    Args:
        mbid: MusicBrainz release ID.

    Returns:
        Release info or None if not found.
    """
    _ensure_musicbrainz()
    _rate_limit()

    try:
        result = musicbrainzngs.get_release_by_id(
            mbid,
            includes=["artists", "labels", "tags"],
        )
    except musicbrainzngs.WebServiceError:
        return None

    release = result.get("release", {})
    return _parse_release(release)


def lookup_song(
    title: str,
    artist: str | None = None,
) -> MusicBrainzResult:
    """Look up a song and gather all available metadata.

    This is the main entry point for MusicBrainz lookups. It searches
    for recordings and extracts all relevant metadata including genre tags.

    Args:
        title: Song title.
        artist: Optional artist name.

    Returns:
        Combined search result with all metadata.
    """
    _ensure_musicbrainz()

    result = MusicBrainzResult()

    # Search for recordings
    recordings = search_recording(title, artist, limit=3)
    result.recordings = recordings

    if not recordings:
        return result

    # Compute confidence based on match quality
    best_recording = recordings[0]
    title_match = title.lower() in best_recording.title.lower()
    artist_match = not artist or (artist.lower() in best_recording.artist.lower())

    if title_match and artist_match:
        result.confidence = 0.9
    elif title_match:
        result.confidence = 0.6
    else:
        result.confidence = 0.3

    # Get releases from recordings
    for recording in recordings:
        result.releases.extend(recording.releases)

    return result


def get_genre_tags(
    title: str,
    artist: str | None = None,
) -> list[str]:
    """Get genre tags for a song from MusicBrainz.

    Args:
        title: Song title.
        artist: Optional artist name.

    Returns:
        List of genre/style tags.
    """
    result = lookup_song(title, artist)

    # Collect all tags
    tags: set[str] = set()

    for recording in result.recordings:
        tags.update(recording.tags)

    for release in result.releases:
        tags.update(release.tags)

    return sorted(tags)


@lru_cache(maxsize=100)
def cached_lookup(
    title: str,
    artist: str | None = None,
) -> MusicBrainzResult:
    """Cached version of lookup_song.

    Results are cached to avoid repeated API calls.

    Args:
        title: Song title.
        artist: Optional artist name.

    Returns:
        Combined search result.
    """
    return lookup_song(title, artist)


def clear_cache() -> None:
    """Clear the lookup cache."""
    cached_lookup.cache_clear()
