"""Tests for genre tag normalization."""

from __future__ import annotations

import pytest

from midi_analyzer.metadata.genres import (
    GENRE_ALIASES,
    GENRE_CATEGORIES,
    SOURCE_WEIGHTS,
    GenreCategory,
    GenreNormalizer,
    GenreResult,
    NormalizedTag,
    get_all_genres,
    get_category,
    get_genres_by_category,
    merge_tags,
    normalize_tag,
    normalize_tags,
    suggest_genres,
)


class TestNormalizeTag:
    """Tests for normalize_tag function."""

    def test_exact_match(self):
        """Test exact match lookup."""
        assert normalize_tag("rock") == "rock"
        assert normalize_tag("hip hop") == "hip-hop"
        assert normalize_tag("jazz") == "jazz"

    def test_case_insensitive(self):
        """Test case insensitivity."""
        assert normalize_tag("ROCK") == "rock"
        assert normalize_tag("Hip Hop") == "hip-hop"
        assert normalize_tag("JAZZ") == "jazz"

    def test_whitespace_handling(self):
        """Test whitespace is trimmed."""
        assert normalize_tag("  rock  ") == "rock"
        assert normalize_tag("\tjazz\n") == "jazz"

    def test_alias_resolution(self):
        """Test alias resolution."""
        assert normalize_tag("hip-hop") == "hip-hop"
        assert normalize_tag("hiphop") == "hip-hop"
        assert normalize_tag("rap") == "hip-hop"

    def test_suffix_removal(self):
        """Test common suffix removal."""
        assert normalize_tag("rock music") == "rock"
        assert normalize_tag("jazz genre") == "jazz"

    def test_unknown_tag(self):
        """Test unknown tag returns None."""
        assert normalize_tag("not a real genre") is None
        assert normalize_tag("xyzabc123") is None

    def test_electronic_variants(self):
        """Test electronic music variants."""
        assert normalize_tag("electronic") == "electronic"
        assert normalize_tag("electronica") == "electronic"
        assert normalize_tag("edm") == "edm"
        assert normalize_tag("electronic dance music") == "edm"

    def test_synth_pop_variants(self):
        """Test synth-pop variants."""
        assert normalize_tag("synth pop") == "synth-pop"
        assert normalize_tag("synthpop") == "synth-pop"
        assert normalize_tag("synth-pop") == "synth-pop"

    def test_drum_and_bass_variants(self):
        """Test drum and bass variants."""
        assert normalize_tag("drum and bass") == "drum and bass"
        assert normalize_tag("drum & bass") == "drum and bass"
        assert normalize_tag("dnb") == "drum and bass"
        assert normalize_tag("d&b") == "drum and bass"

    def test_progressive_rock_variants(self):
        """Test progressive rock variants."""
        assert normalize_tag("progressive rock") == "progressive rock"
        assert normalize_tag("prog rock") == "progressive rock"
        assert normalize_tag("prog") == "progressive rock"

    def test_post_genres(self):
        """Test post-* genre variants."""
        assert normalize_tag("post-punk") == "post-punk"
        assert normalize_tag("post punk") == "post-punk"
        assert normalize_tag("post-rock") == "post-rock"
        assert normalize_tag("post rock") == "post-rock"


class TestGetCategory:
    """Tests for get_category function."""

    def test_rock_genres(self):
        """Test rock genre categories."""
        assert get_category("rock") == GenreCategory.ROCK
        assert get_category("classic rock") == GenreCategory.ROCK
        assert get_category("alternative rock") == GenreCategory.ROCK
        assert get_category("grunge") == GenreCategory.ROCK

    def test_electronic_genres(self):
        """Test electronic genre categories."""
        assert get_category("electronic") == GenreCategory.ELECTRONIC
        assert get_category("house") == GenreCategory.ELECTRONIC
        assert get_category("techno") == GenreCategory.ELECTRONIC
        assert get_category("drum and bass") == GenreCategory.ELECTRONIC

    def test_hip_hop_genres(self):
        """Test hip-hop genre categories."""
        assert get_category("hip-hop") == GenreCategory.HIP_HOP
        assert get_category("trap") == GenreCategory.HIP_HOP
        assert get_category("grime") == GenreCategory.HIP_HOP

    def test_unknown_returns_other(self):
        """Test unknown genre returns OTHER."""
        assert get_category("unknown genre") == GenreCategory.OTHER
        assert get_category("") == GenreCategory.OTHER


class TestNormalizeTags:
    """Tests for normalize_tags function."""

    def test_basic_normalization(self):
        """Test basic tag normalization."""
        result = normalize_tags(["rock", "pop", "jazz"])
        assert len(result) == 3
        canonicals = {t.canonical for t in result}
        assert canonicals == {"rock", "pop", "jazz"}

    def test_deduplication(self):
        """Test duplicate tags are merged."""
        result = normalize_tags(["hip hop", "hip-hop", "hiphop"])
        assert len(result) == 1
        assert result[0].canonical == "hip-hop"
        assert set(result[0].raw_tags) == {"hip hop", "hip-hop", "hiphop"}

    def test_source_tracking(self):
        """Test source is tracked."""
        result = normalize_tags(["rock", "pop"], source="musicbrainz")
        for tag in result:
            assert tag.sources == ["musicbrainz"]

    def test_confidence_from_source(self):
        """Test confidence is based on source."""
        mb_result = normalize_tags(["rock"], source="musicbrainz")
        user_result = normalize_tags(["rock"], source="user")

        assert mb_result[0].confidence == 1.0
        assert user_result[0].confidence == 0.5

    def test_filters_unknown_tags(self):
        """Test unknown tags are filtered."""
        result = normalize_tags(["rock", "not a genre", "jazz"])
        assert len(result) == 2
        canonicals = {t.canonical for t in result}
        assert canonicals == {"rock", "jazz"}

    def test_empty_list(self):
        """Test empty list returns empty."""
        result = normalize_tags([])
        assert result == []


class TestMergeTags:
    """Tests for merge_tags function."""

    def test_single_source(self):
        """Test merging from single source."""
        result = merge_tags([
            (["rock", "alternative"], "musicbrainz"),
        ])

        assert result.primary is not None
        assert result.primary.canonical in ["rock", "alternative rock"]
        assert len(result.all_tags) == 2

    def test_multiple_sources_agreement(self):
        """Test confidence increases with source agreement."""
        result = merge_tags([
            (["rock"], "musicbrainz"),
            (["rock"], "discogs"),
            (["rock"], "lastfm"),
        ])

        assert result.primary is not None
        assert result.primary.canonical == "rock"
        assert len(result.primary.sources) == 3
        assert result.overall_confidence == 1.0

    def test_multiple_sources_mixed(self):
        """Test mixed tags from multiple sources."""
        result = merge_tags([
            (["rock", "pop"], "musicbrainz"),
            (["rock", "electronic"], "discogs"),
        ])

        # Rock should be primary (appears in both)
        assert result.primary is not None
        assert result.primary.canonical == "rock"
        assert len(result.primary.sources) == 2

    def test_raw_tags_preserved(self):
        """Test raw tags are preserved."""
        result = merge_tags([
            (["hip hop", "rap"], "musicbrainz"),
            (["hip-hop"], "discogs"),
        ])

        assert "hip hop" in result.raw_tags
        assert "rap" in result.raw_tags
        assert "hip-hop" in result.raw_tags

    def test_overall_confidence_calculation(self):
        """Test overall confidence is calculated correctly."""
        # Single source
        result1 = merge_tags([(["rock"], "musicbrainz")])
        assert result1.overall_confidence == 1.0

        # Multiple sources, partial agreement
        result2 = merge_tags([
            (["rock"], "musicbrainz"),
            (["pop"], "discogs"),
        ])
        assert result2.overall_confidence == 0.5

    def test_empty_sources(self):
        """Test empty sources."""
        result = merge_tags([])
        assert result.primary is None
        assert result.all_tags == []
        assert result.overall_confidence == 0.0

    def test_secondary_genres(self):
        """Test secondary genres are captured."""
        result = merge_tags([
            (["rock", "pop", "electronic", "jazz", "blues"], "musicbrainz"),
        ])

        assert result.primary is not None
        assert len(result.secondary) == 3  # Max 3 secondary


class TestSuggestGenres:
    """Tests for suggest_genres function."""

    def test_basic_suggestion(self):
        """Test basic genre suggestion."""
        suggestions = suggest_genres("rock")
        assert "rock" in suggestions
        assert len(suggestions) > 0

    def test_partial_match(self):
        """Test partial string matching."""
        suggestions = suggest_genres("prog")
        assert "progressive rock" in suggestions

    def test_limit_results(self):
        """Test result limiting."""
        suggestions = suggest_genres("rock", limit=2)
        assert len(suggestions) <= 2

    def test_empty_partial(self):
        """Test empty partial returns all (up to limit)."""
        suggestions = suggest_genres("", limit=5)
        assert len(suggestions) <= 5


class TestGetAllGenres:
    """Tests for get_all_genres function."""

    def test_returns_list(self):
        """Test returns list of genres."""
        genres = get_all_genres()
        assert isinstance(genres, list)
        assert len(genres) > 0

    def test_all_unique(self):
        """Test all genres are unique."""
        genres = get_all_genres()
        assert len(genres) == len(set(genres))

    def test_sorted(self):
        """Test genres are sorted."""
        genres = get_all_genres()
        assert genres == sorted(genres)


class TestGetGenresByCategory:
    """Tests for get_genres_by_category function."""

    def test_rock_category(self):
        """Test rock category genres."""
        genres = get_genres_by_category(GenreCategory.ROCK)
        assert "rock" in genres
        assert "classic rock" in genres
        assert "grunge" in genres

    def test_electronic_category(self):
        """Test electronic category genres."""
        genres = get_genres_by_category(GenreCategory.ELECTRONIC)
        assert "electronic" in genres
        assert "house" in genres
        assert "techno" in genres

    def test_sorted(self):
        """Test genres are sorted."""
        genres = get_genres_by_category(GenreCategory.ROCK)
        assert genres == sorted(genres)


class TestGenreNormalizer:
    """Tests for GenreNormalizer class."""

    def test_normalize_single(self):
        """Test normalizing single tag."""
        normalizer = GenreNormalizer()
        result = normalizer.normalize("rock")

        assert result is not None
        assert result.canonical == "rock"
        assert result.category == GenreCategory.ROCK

    def test_normalize_unknown(self):
        """Test normalizing unknown tag."""
        normalizer = GenreNormalizer()
        result = normalizer.normalize("not a genre")
        assert result is None

    def test_normalize_batch(self):
        """Test batch normalization."""
        normalizer = GenreNormalizer()
        results = normalizer.normalize_batch(["rock", "pop", "unknown", "jazz"])

        assert len(results) == 3
        canonicals = {t.canonical for t in results}
        assert canonicals == {"rock", "pop", "jazz"}

    def test_normalize_from_sources(self):
        """Test normalizing from multiple sources."""
        normalizer = GenreNormalizer()
        result = normalizer.normalize_from_sources({
            "musicbrainz": ["rock", "alternative"],
            "discogs": ["rock", "indie"],
        })

        assert result.primary is not None
        assert result.primary.canonical == "rock"
        assert len(result.primary.sources) == 2

    def test_caching(self):
        """Test normalization caching."""
        normalizer = GenreNormalizer()

        # First call
        result1 = normalizer.normalize("rock")

        # Second call (should use cache)
        result2 = normalizer.normalize("rock")

        assert result1 is not None
        assert result2 is not None
        assert result1.canonical == result2.canonical

    def test_cache_clear(self):
        """Test cache clearing."""
        normalizer = GenreNormalizer()

        normalizer.normalize("rock")
        assert len(normalizer._cache) > 0

        normalizer.clear_cache()
        assert len(normalizer._cache) == 0


class TestNormalizedTag:
    """Tests for NormalizedTag dataclass."""

    def test_creation(self):
        """Test creating NormalizedTag."""
        tag = NormalizedTag(
            canonical="rock",
            category=GenreCategory.ROCK,
            raw_tags=["rock", "Rock"],
            confidence=0.9,
            sources=["musicbrainz"],
        )

        assert tag.canonical == "rock"
        assert tag.category == GenreCategory.ROCK
        assert tag.raw_tags == ["rock", "Rock"]
        assert tag.confidence == 0.9
        assert tag.sources == ["musicbrainz"]

    def test_defaults(self):
        """Test default values."""
        tag = NormalizedTag(canonical="rock", category=GenreCategory.ROCK)

        assert tag.raw_tags == []
        assert tag.confidence == 1.0
        assert tag.sources == []


class TestGenreResult:
    """Tests for GenreResult dataclass."""

    def test_creation(self):
        """Test creating GenreResult."""
        primary = NormalizedTag(canonical="rock", category=GenreCategory.ROCK)
        result = GenreResult(
            primary=primary,
            secondary=[],
            all_tags=[primary],
            raw_tags=["rock"],
            overall_confidence=0.9,
        )

        assert result.primary == primary
        assert result.overall_confidence == 0.9

    def test_defaults(self):
        """Test default values."""
        result = GenreResult()

        assert result.primary is None
        assert result.secondary == []
        assert result.all_tags == []
        assert result.raw_tags == []
        assert result.overall_confidence == 0.0


class TestGenreCategory:
    """Tests for GenreCategory enum."""

    def test_all_categories(self):
        """Test all expected categories exist."""
        categories = list(GenreCategory)

        assert GenreCategory.ROCK in categories
        assert GenreCategory.POP in categories
        assert GenreCategory.ELECTRONIC in categories
        assert GenreCategory.JAZZ in categories
        assert GenreCategory.CLASSICAL in categories
        assert GenreCategory.HIP_HOP in categories
        assert GenreCategory.OTHER in categories

    def test_string_values(self):
        """Test categories have string values."""
        assert GenreCategory.ROCK.value == "rock"
        assert GenreCategory.HIP_HOP.value == "hip-hop"
        assert GenreCategory.RNB.value == "r&b"


class TestTaxonomyConsistency:
    """Tests for taxonomy consistency."""

    def test_all_aliases_map_to_categories(self):
        """Test all canonical names have categories."""
        canonical_genres = set(GENRE_ALIASES.values())
        categorized_genres = set(GENRE_CATEGORIES.keys())

        # All canonical genres should have a category
        uncategorized = canonical_genres - categorized_genres
        assert len(uncategorized) == 0, f"Uncategorized genres: {uncategorized}"

    def test_all_sources_have_weights(self):
        """Test expected sources have weights."""
        expected_sources = ["musicbrainz", "discogs", "lastfm", "spotify", "user"]
        for source in expected_sources:
            assert source in SOURCE_WEIGHTS

    def test_source_weights_valid(self):
        """Test source weights are between 0 and 1."""
        for source, weight in SOURCE_WEIGHTS.items():
            assert 0 <= weight <= 1, f"Invalid weight for {source}: {weight}"


class TestRealWorldScenarios:
    """Tests for real-world usage scenarios."""

    def test_musicbrainz_tags(self):
        """Test tags from MusicBrainz."""
        normalizer = GenreNormalizer()
        result = normalizer.normalize_from_sources({
            "musicbrainz": [
                "electronic",
                "ambient",
                "electronica",
                "downtempo",
            ],
        })

        assert result.primary is not None
        assert result.primary.category == GenreCategory.ELECTRONIC

    def test_mixed_quality_sources(self):
        """Test mixing high and low quality sources."""
        normalizer = GenreNormalizer()
        result = normalizer.normalize_from_sources({
            "musicbrainz": ["rock"],
            "filename": ["rock_song_metal"],  # Won't match
            "user": ["hard rock"],
        })

        # Rock should be primary despite filename tag
        assert result.primary is not None
        assert result.primary.canonical == "rock"

    def test_subgenre_specificity(self):
        """Test subgenre vs parent genre."""
        normalizer = GenreNormalizer()
        result = normalizer.normalize_from_sources({
            "musicbrainz": ["progressive rock", "rock"],
        })

        # Both should be present
        canonicals = {t.canonical for t in result.all_tags}
        assert "progressive rock" in canonicals
        assert "rock" in canonicals

    def test_cross_genre_tags(self):
        """Test songs with multiple genres."""
        normalizer = GenreNormalizer()
        result = normalizer.normalize_from_sources({
            "musicbrainz": ["jazz fusion", "rock"],
            "discogs": ["jazz", "progressive rock"],
        })

        # Should have tags from both categories
        categories = {t.category for t in result.all_tags}
        assert GenreCategory.JAZZ in categories
        assert GenreCategory.ROCK in categories
