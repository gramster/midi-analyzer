"""Tests for MusicBrainz integration."""

from unittest.mock import MagicMock, patch

import pytest

from midi_analyzer.metadata.musicbrainz import (
    ArtistInfo,
    MusicBrainzResult,
    RecordingInfo,
    ReleaseInfo,
    _extract_tags,
    _parse_artist,
    _parse_recording,
    _parse_release,
    get_genre_tags,
    lookup_song,
    search_artist,
    search_recording,
    search_release,
)


class TestDataclasses:
    """Tests for MusicBrainz dataclasses."""

    def test_artist_info(self):
        """Test ArtistInfo creation."""
        artist = ArtistInfo(
            mbid="test-mbid",
            name="Test Artist",
            sort_name="Artist, Test",
            type="Group",
            country="US",
            tags=["rock", "pop"],
        )

        assert artist.mbid == "test-mbid"
        assert artist.name == "Test Artist"
        assert artist.sort_name == "Artist, Test"
        assert artist.type == "Group"
        assert "rock" in artist.tags

    def test_release_info(self):
        """Test ReleaseInfo creation."""
        release = ReleaseInfo(
            mbid="release-mbid",
            title="Test Album",
            artist="Test Artist",
            date="2020-01-01",
            country="US",
            status="Official",
            label="Test Label",
        )

        assert release.mbid == "release-mbid"
        assert release.title == "Test Album"
        assert release.date == "2020-01-01"

    def test_recording_info(self):
        """Test RecordingInfo creation."""
        recording = RecordingInfo(
            mbid="recording-mbid",
            title="Test Song",
            artist="Test Artist",
            length_ms=180000,
            tags=["electronic"],
        )

        assert recording.mbid == "recording-mbid"
        assert recording.title == "Test Song"
        assert recording.length_ms == 180000

    def test_musicbrainz_result(self):
        """Test MusicBrainzResult creation."""
        result = MusicBrainzResult(confidence=0.9)
        assert result.confidence == 0.9
        assert result.recordings == []
        assert result.artists == []
        assert result.releases == []


class TestTagExtraction:
    """Tests for tag extraction."""

    def test_extract_tags_empty(self):
        """Test extracting tags from empty entity."""
        entity: dict = {}
        tags = _extract_tags(entity)
        assert tags == []

    def test_extract_tags_with_tags(self):
        """Test extracting tags from entity with tags."""
        entity = {
            "tag-list": [
                {"name": "rock", "count": "10"},
                {"name": "pop", "count": "5"},
            ]
        }
        tags = _extract_tags(entity)
        assert tags == ["rock", "pop"]

    def test_extract_tags_empty_names(self):
        """Test extracting tags with empty names."""
        entity = {"tag-list": [{"name": ""}, {"name": "rock"}]}
        tags = _extract_tags(entity)
        assert tags == ["rock"]


class TestParsers:
    """Tests for entity parsers."""

    def test_parse_artist(self):
        """Test parsing artist data."""
        data = {
            "id": "artist-id",
            "name": "Test Artist",
            "sort-name": "Artist, Test",
            "type": "Person",
            "country": "GB",
            "disambiguation": "UK singer",
            "tag-list": [{"name": "indie"}],
        }

        artist = _parse_artist(data)

        assert artist.mbid == "artist-id"
        assert artist.name == "Test Artist"
        assert artist.sort_name == "Artist, Test"
        assert artist.type == "Person"
        assert artist.country == "GB"
        assert "indie" in artist.tags

    def test_parse_artist_minimal(self):
        """Test parsing minimal artist data."""
        data = {"id": "id", "name": "Name"}
        artist = _parse_artist(data)

        assert artist.mbid == "id"
        assert artist.name == "Name"
        assert artist.type == ""
        assert artist.tags == []

    def test_parse_release(self):
        """Test parsing release data."""
        data = {
            "id": "release-id",
            "title": "Album Title",
            "date": "2020",
            "country": "US",
            "status": "Official",
            "barcode": "123456789",
            "artist-credit": [{"artist": {"name": "Artist Name"}}],
            "label-info-list": [
                {"label": {"name": "Label Name"}, "catalog-number": "CAT-001"}
            ],
        }

        release = _parse_release(data)

        assert release.mbid == "release-id"
        assert release.title == "Album Title"
        assert release.artist == "Artist Name"
        assert release.label == "Label Name"
        assert release.catalog_number == "CAT-001"

    def test_parse_recording(self):
        """Test parsing recording data."""
        data = {
            "id": "recording-id",
            "title": "Song Title",
            "length": 180000,
            "artist-credit": [{"artist": {"name": "Artist"}}],
            "release-list": [{"id": "release-1", "title": "Album"}],
            "tag-list": [{"name": "rock"}],
            "isrc-list": ["USRC12345678"],
        }

        recording = _parse_recording(data)

        assert recording.mbid == "recording-id"
        assert recording.title == "Song Title"
        assert recording.artist == "Artist"
        assert recording.length_ms == 180000
        assert len(recording.releases) == 1
        assert recording.isrcs == ["USRC12345678"]


class TestSearchFunctions:
    """Tests for search functions with mocked API."""

    @patch("midi_analyzer.metadata.musicbrainz.musicbrainzngs")
    @patch("midi_analyzer.metadata.musicbrainz.HAS_MUSICBRAINZ", True)
    @patch("midi_analyzer.metadata.musicbrainz._rate_limit")
    def test_search_recording(self, mock_rate_limit, mock_mb):
        """Test searching for recordings."""
        mock_mb.search_recordings.return_value = {
            "recording-list": [
                {
                    "id": "rec-1",
                    "title": "Test Song",
                    "artist-credit": [{"artist": {"name": "Test Artist"}}],
                }
            ]
        }

        recordings = search_recording("Test Song", "Test Artist")

        assert len(recordings) == 1
        assert recordings[0].title == "Test Song"
        mock_mb.search_recordings.assert_called_once()

    @patch("midi_analyzer.metadata.musicbrainz.musicbrainzngs")
    @patch("midi_analyzer.metadata.musicbrainz.HAS_MUSICBRAINZ", True)
    @patch("midi_analyzer.metadata.musicbrainz._rate_limit")
    def test_search_recording_error(self, mock_rate_limit, mock_mb):
        """Test search handling API errors."""
        mock_mb.WebServiceError = Exception
        mock_mb.search_recordings.side_effect = Exception("API error")

        recordings = search_recording("Test Song")

        assert recordings == []

    @patch("midi_analyzer.metadata.musicbrainz.musicbrainzngs")
    @patch("midi_analyzer.metadata.musicbrainz.HAS_MUSICBRAINZ", True)
    @patch("midi_analyzer.metadata.musicbrainz._rate_limit")
    def test_search_artist(self, mock_rate_limit, mock_mb):
        """Test searching for artists."""
        mock_mb.search_artists.return_value = {
            "artist-list": [
                {"id": "art-1", "name": "Test Artist", "type": "Group"}
            ]
        }

        artists = search_artist("Test Artist")

        assert len(artists) == 1
        assert artists[0].name == "Test Artist"

    @patch("midi_analyzer.metadata.musicbrainz.musicbrainzngs")
    @patch("midi_analyzer.metadata.musicbrainz.HAS_MUSICBRAINZ", True)
    @patch("midi_analyzer.metadata.musicbrainz._rate_limit")
    def test_search_release(self, mock_rate_limit, mock_mb):
        """Test searching for releases."""
        mock_mb.search_releases.return_value = {
            "release-list": [{"id": "rel-1", "title": "Test Album"}]
        }

        releases = search_release("Test Album")

        assert len(releases) == 1
        assert releases[0].title == "Test Album"


class TestLookup:
    """Tests for lookup functions."""

    @patch("midi_analyzer.metadata.musicbrainz.search_recording")
    def test_lookup_song_found(self, mock_search):
        """Test looking up a song that's found."""
        mock_search.return_value = [
            RecordingInfo(
                mbid="rec-1",
                title="Test Song",
                artist="Test Artist",
                tags=["rock"],
            )
        ]

        result = lookup_song("Test Song", "Test Artist")

        assert result.confidence >= 0.6
        assert len(result.recordings) == 1

    @patch("midi_analyzer.metadata.musicbrainz.search_recording")
    def test_lookup_song_not_found(self, mock_search):
        """Test looking up a song that's not found."""
        mock_search.return_value = []

        result = lookup_song("Unknown Song")

        assert result.confidence == 0.0
        assert len(result.recordings) == 0

    @patch("midi_analyzer.metadata.musicbrainz.search_recording")
    def test_lookup_song_partial_match(self, mock_search):
        """Test looking up a song with partial match."""
        mock_search.return_value = [
            RecordingInfo(
                mbid="rec-1",
                title="Completely Different Song",  # No matching title
                artist="Test Artist",
            )
        ]

        result = lookup_song("Test Song", "Test Artist")

        # Should have lower confidence when title doesn't match
        assert result.confidence <= 0.6


class TestGenreTags:
    """Tests for genre tag retrieval."""

    @patch("midi_analyzer.metadata.musicbrainz.lookup_song")
    def test_get_genre_tags(self, mock_lookup):
        """Test getting genre tags for a song."""
        mock_lookup.return_value = MusicBrainzResult(
            recordings=[
                RecordingInfo(mbid="1", title="Song", tags=["rock", "alternative"]),
            ],
            releases=[
                ReleaseInfo(mbid="2", title="Album", tags=["indie"]),
            ],
        )

        tags = get_genre_tags("Song", "Artist")

        assert "rock" in tags
        assert "alternative" in tags
        assert "indie" in tags

    @patch("midi_analyzer.metadata.musicbrainz.lookup_song")
    def test_get_genre_tags_empty(self, mock_lookup):
        """Test getting genre tags when none found."""
        mock_lookup.return_value = MusicBrainzResult()

        tags = get_genre_tags("Unknown", None)

        assert tags == []

    @patch("midi_analyzer.metadata.musicbrainz.lookup_song")
    def test_get_genre_tags_deduplication(self, mock_lookup):
        """Test that duplicate tags are removed."""
        mock_lookup.return_value = MusicBrainzResult(
            recordings=[
                RecordingInfo(mbid="1", title="Song", tags=["rock", "pop"]),
                RecordingInfo(mbid="2", title="Song", tags=["rock", "indie"]),
            ],
        )

        tags = get_genre_tags("Song")

        # Should not have duplicates
        assert len(tags) == len(set(tags))
        assert "rock" in tags


class TestImportCheck:
    """Tests for import checking."""

    def test_has_musicbrainz_flag(self):
        """Test that HAS_MUSICBRAINZ is set correctly."""
        # This test just verifies the flag exists and is boolean
        from midi_analyzer.metadata.musicbrainz import HAS_MUSICBRAINZ

        assert isinstance(HAS_MUSICBRAINZ, bool)


class TestRateLimiting:
    """Tests for rate limiting."""

    @patch("midi_analyzer.metadata.musicbrainz.time.sleep")
    @patch("midi_analyzer.metadata.musicbrainz.time.time")
    def test_rate_limit_sleeps(self, mock_time, mock_sleep):
        """Test that rate limiting sleeps when needed."""
        from midi_analyzer.metadata.musicbrainz import _rate_limit, _last_request_time
        import midi_analyzer.metadata.musicbrainz as mb

        # Set up mock times
        mb._last_request_time = 10.0
        mock_time.return_value = 10.5  # Only 0.5 seconds elapsed

        _rate_limit()

        # Should sleep for remaining time
        mock_sleep.assert_called_once()
        sleep_time = mock_sleep.call_args[0][0]
        assert sleep_time > 0 and sleep_time <= 1.0
