"""Genre and tag retrieval from web APIs."""

from midi_analyzer.metadata.cache import (
    APICache,
    CacheEntry,
    CacheStats,
    RateLimitState,
    close_cache,
    get_cache,
)
from midi_analyzer.metadata.musicbrainz import (
    ArtistInfo,
    MusicBrainzResult,
    RecordingInfo,
    ReleaseInfo,
    cached_lookup,
    clear_cache,
    get_artist_by_mbid,
    get_genre_tags,
    get_recording_by_mbid,
    get_release_by_mbid,
    lookup_song,
    search_artist,
    search_recording,
    search_release,
)

__all__ = [
    # Cache
    "APICache",
    "CacheEntry",
    "CacheStats",
    "RateLimitState",
    "close_cache",
    "get_cache",
    # MusicBrainz
    "ArtistInfo",
    "MusicBrainzResult",
    "RecordingInfo",
    "ReleaseInfo",
    "cached_lookup",
    "clear_cache",
    "get_artist_by_mbid",
    "get_genre_tags",
    "get_recording_by_mbid",
    "get_release_by_mbid",
    "lookup_song",
    "search_artist",
    "search_recording",
    "search_release",
]