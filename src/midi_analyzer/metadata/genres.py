"""Genre tag normalization and taxonomy mapping."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class GenreCategory(str, Enum):
    """High-level genre categories."""

    ROCK = "rock"
    POP = "pop"
    ELECTRONIC = "electronic"
    JAZZ = "jazz"
    CLASSICAL = "classical"
    HIP_HOP = "hip-hop"
    RNB = "r&b"
    COUNTRY = "country"
    FOLK = "folk"
    BLUES = "blues"
    METAL = "metal"
    PUNK = "punk"
    REGGAE = "reggae"
    LATIN = "latin"
    WORLD = "world"
    SOUL = "soul"
    FUNK = "funk"
    AMBIENT = "ambient"
    EXPERIMENTAL = "experimental"
    SOUNDTRACK = "soundtrack"
    OTHER = "other"


@dataclass
class NormalizedTag:
    """A normalized genre tag.

    Attributes:
        canonical: The canonical/normalized tag name.
        category: High-level genre category.
        raw_tags: Original raw tags that mapped to this.
        confidence: Confidence score (0-1).
        sources: Sources that provided this tag.
    """

    canonical: str
    category: GenreCategory
    raw_tags: list[str] = field(default_factory=list)
    confidence: float = 1.0
    sources: list[str] = field(default_factory=list)


@dataclass
class GenreResult:
    """Result of genre normalization.

    Attributes:
        primary: Primary/most confident genre.
        secondary: Secondary genres.
        all_tags: All normalized tags.
        raw_tags: Original raw tags before normalization.
        overall_confidence: Overall confidence based on source agreement.
    """

    primary: NormalizedTag | None = None
    secondary: list[NormalizedTag] = field(default_factory=list)
    all_tags: list[NormalizedTag] = field(default_factory=list)
    raw_tags: list[str] = field(default_factory=list)
    overall_confidence: float = 0.0


# Canonical genre taxonomy mapping
# Maps variations/aliases to canonical names
GENRE_ALIASES: dict[str, str] = {
    # Rock variations
    "rock": "rock",
    "rock and roll": "rock",
    "rock & roll": "rock",
    "rock n roll": "rock",
    "classic rock": "classic rock",
    "hard rock": "hard rock",
    "soft rock": "soft rock",
    "progressive rock": "progressive rock",
    "prog rock": "progressive rock",
    "prog": "progressive rock",
    "alternative rock": "alternative rock",
    "alt rock": "alternative rock",
    "alternative": "alternative rock",
    "indie rock": "indie rock",
    "indie": "indie rock",
    "grunge": "grunge",
    "psychedelic rock": "psychedelic rock",
    "psychedelic": "psychedelic rock",
    "garage rock": "garage rock",
    "southern rock": "southern rock",
    "glam rock": "glam rock",
    "art rock": "art rock",
    # Pop variations
    "pop": "pop",
    "pop music": "pop",
    "synth pop": "synth-pop",
    "synthpop": "synth-pop",
    "synth-pop": "synth-pop",
    "electropop": "electro-pop",
    "electro pop": "electro-pop",
    "electro-pop": "electro-pop",
    "dance pop": "dance-pop",
    "dance-pop": "dance-pop",
    "art pop": "art pop",
    "indie pop": "indie pop",
    "chamber pop": "chamber pop",
    "dream pop": "dream pop",
    "power pop": "power pop",
    "teen pop": "teen pop",
    "k-pop": "k-pop",
    "kpop": "k-pop",
    "j-pop": "j-pop",
    "jpop": "j-pop",
    # Electronic variations
    "electronic": "electronic",
    "electronica": "electronic",
    "edm": "edm",
    "electronic dance music": "edm",
    "house": "house",
    "deep house": "deep house",
    "tech house": "tech house",
    "progressive house": "progressive house",
    "techno": "techno",
    "trance": "trance",
    "progressive trance": "progressive trance",
    "psytrance": "psytrance",
    "psy trance": "psytrance",
    "drum and bass": "drum and bass",
    "drum & bass": "drum and bass",
    "dnb": "drum and bass",
    "d&b": "drum and bass",
    "dubstep": "dubstep",
    "breakbeat": "breakbeat",
    "breaks": "breakbeat",
    "idm": "idm",
    "intelligent dance music": "idm",
    "downtempo": "downtempo",
    "chillout": "chillout",
    "chill out": "chillout",
    "chill-out": "chillout",
    "trip hop": "trip-hop",
    "trip-hop": "trip-hop",
    "triphop": "trip-hop",
    # Jazz variations
    "jazz": "jazz",
    "smooth jazz": "smooth jazz",
    "jazz fusion": "jazz fusion",
    "fusion": "jazz fusion",
    "bebop": "bebop",
    "be-bop": "bebop",
    "free jazz": "free jazz",
    "cool jazz": "cool jazz",
    "swing": "swing",
    "big band": "big band",
    "latin jazz": "latin jazz",
    "acid jazz": "acid jazz",
    "nu jazz": "nu-jazz",
    "nu-jazz": "nu-jazz",
    # Classical variations
    "classical": "classical",
    "classical music": "classical",
    "baroque": "baroque",
    "romantic": "romantic",
    "contemporary classical": "contemporary classical",
    "modern classical": "contemporary classical",
    "minimalism": "minimalism",
    "minimalist": "minimalism",
    "opera": "opera",
    "symphony": "symphony",
    "orchestral": "orchestral",
    "chamber music": "chamber music",
    "choral": "choral",
    # Hip-hop variations
    "hip hop": "hip-hop",
    "hip-hop": "hip-hop",
    "hiphop": "hip-hop",
    "rap": "hip-hop",
    "trap": "trap",
    "boom bap": "boom bap",
    "gangsta rap": "gangsta rap",
    "conscious hip hop": "conscious hip-hop",
    "alternative hip hop": "alternative hip-hop",
    "underground hip hop": "underground hip-hop",
    "east coast hip hop": "east coast hip-hop",
    "west coast hip hop": "west coast hip-hop",
    "southern hip hop": "southern hip-hop",
    "crunk": "crunk",
    "grime": "grime",
    # R&B variations
    "r&b": "r&b",
    "rnb": "r&b",
    "rhythm and blues": "r&b",
    "contemporary r&b": "contemporary r&b",
    "neo soul": "neo-soul",
    "neo-soul": "neo-soul",
    "new jack swing": "new jack swing",
    # Country variations
    "country": "country",
    "country music": "country",
    "country rock": "country rock",
    "outlaw country": "outlaw country",
    "alt country": "alt-country",
    "alt-country": "alt-country",
    "alternative country": "alt-country",
    "americana": "americana",
    "bluegrass": "bluegrass",
    "honky tonk": "honky tonk",
    # Folk variations
    "folk": "folk",
    "folk music": "folk",
    "folk rock": "folk rock",
    "indie folk": "indie folk",
    "contemporary folk": "contemporary folk",
    "traditional folk": "traditional folk",
    "singer-songwriter": "singer-songwriter",
    "singer songwriter": "singer-songwriter",
    # Blues variations
    "blues": "blues",
    "blues music": "blues",
    "electric blues": "electric blues",
    "delta blues": "delta blues",
    "chicago blues": "chicago blues",
    "blues rock": "blues rock",
    # Metal variations
    "metal": "metal",
    "heavy metal": "heavy metal",
    "thrash metal": "thrash metal",
    "thrash": "thrash metal",
    "death metal": "death metal",
    "black metal": "black metal",
    "doom metal": "doom metal",
    "power metal": "power metal",
    "progressive metal": "progressive metal",
    "prog metal": "progressive metal",
    "nu metal": "nu-metal",
    "nu-metal": "nu-metal",
    "metalcore": "metalcore",
    "deathcore": "deathcore",
    "symphonic metal": "symphonic metal",
    # Punk variations
    "punk": "punk",
    "punk rock": "punk rock",
    "hardcore punk": "hardcore punk",
    "hardcore": "hardcore punk",
    "post-punk": "post-punk",
    "post punk": "post-punk",
    "pop punk": "pop punk",
    "pop-punk": "pop punk",
    "emo": "emo",
    "screamo": "screamo",
    "ska punk": "ska punk",
    # Reggae variations
    "reggae": "reggae",
    "dub": "dub",
    "ska": "ska",
    "dancehall": "dancehall",
    "roots reggae": "roots reggae",
    "rocksteady": "rocksteady",
    # Latin variations
    "latin": "latin",
    "latin music": "latin",
    "salsa": "salsa",
    "bachata": "bachata",
    "merengue": "merengue",
    "reggaeton": "reggaeton",
    "reggaetón": "reggaeton",
    "bossa nova": "bossa nova",
    "samba": "samba",
    "tango": "tango",
    "cumbia": "cumbia",
    "latin pop": "latin pop",
    # World music variations
    "world": "world",
    "world music": "world",
    "afrobeat": "afrobeat",
    "afropop": "afropop",
    "celtic": "celtic",
    "flamenco": "flamenco",
    "indian classical": "indian classical",
    "middle eastern": "middle eastern",
    # Soul/Funk variations
    "soul": "soul",
    "soul music": "soul",
    "motown": "motown",
    "northern soul": "northern soul",
    "funk": "funk",
    "p-funk": "p-funk",
    "disco": "disco",
    "nu disco": "nu-disco",
    "nu-disco": "nu-disco",
    # Ambient variations
    "ambient": "ambient",
    "ambient music": "ambient",
    "dark ambient": "dark ambient",
    "drone": "drone",
    "new age": "new age",
    # Experimental variations
    "experimental": "experimental",
    "avant-garde": "avant-garde",
    "avant garde": "avant-garde",
    "noise": "noise",
    "industrial": "industrial",
    "post-rock": "post-rock",
    "post rock": "post-rock",
    "math rock": "math rock",
    "shoegaze": "shoegaze",
    # Soundtrack variations
    "soundtrack": "soundtrack",
    "film score": "film score",
    "film soundtrack": "soundtrack",
    "video game music": "video game music",
    "game music": "video game music",
    "vgm": "video game music",
    "anime": "anime soundtrack",
    "anime soundtrack": "anime soundtrack",
}

# Map canonical genres to categories
GENRE_CATEGORIES: dict[str, GenreCategory] = {
    # Rock
    "rock": GenreCategory.ROCK,
    "classic rock": GenreCategory.ROCK,
    "hard rock": GenreCategory.ROCK,
    "soft rock": GenreCategory.ROCK,
    "progressive rock": GenreCategory.ROCK,
    "alternative rock": GenreCategory.ROCK,
    "indie rock": GenreCategory.ROCK,
    "grunge": GenreCategory.ROCK,
    "psychedelic rock": GenreCategory.ROCK,
    "garage rock": GenreCategory.ROCK,
    "southern rock": GenreCategory.ROCK,
    "glam rock": GenreCategory.ROCK,
    "art rock": GenreCategory.ROCK,
    # Pop
    "pop": GenreCategory.POP,
    "synth-pop": GenreCategory.POP,
    "electro-pop": GenreCategory.POP,
    "dance-pop": GenreCategory.POP,
    "art pop": GenreCategory.POP,
    "indie pop": GenreCategory.POP,
    "chamber pop": GenreCategory.POP,
    "dream pop": GenreCategory.POP,
    "power pop": GenreCategory.POP,
    "teen pop": GenreCategory.POP,
    "k-pop": GenreCategory.POP,
    "j-pop": GenreCategory.POP,
    # Electronic
    "electronic": GenreCategory.ELECTRONIC,
    "edm": GenreCategory.ELECTRONIC,
    "house": GenreCategory.ELECTRONIC,
    "deep house": GenreCategory.ELECTRONIC,
    "tech house": GenreCategory.ELECTRONIC,
    "progressive house": GenreCategory.ELECTRONIC,
    "techno": GenreCategory.ELECTRONIC,
    "trance": GenreCategory.ELECTRONIC,
    "progressive trance": GenreCategory.ELECTRONIC,
    "psytrance": GenreCategory.ELECTRONIC,
    "drum and bass": GenreCategory.ELECTRONIC,
    "dubstep": GenreCategory.ELECTRONIC,
    "breakbeat": GenreCategory.ELECTRONIC,
    "idm": GenreCategory.ELECTRONIC,
    "downtempo": GenreCategory.ELECTRONIC,
    "chillout": GenreCategory.ELECTRONIC,
    "trip-hop": GenreCategory.ELECTRONIC,
    # Jazz
    "jazz": GenreCategory.JAZZ,
    "smooth jazz": GenreCategory.JAZZ,
    "jazz fusion": GenreCategory.JAZZ,
    "bebop": GenreCategory.JAZZ,
    "free jazz": GenreCategory.JAZZ,
    "cool jazz": GenreCategory.JAZZ,
    "swing": GenreCategory.JAZZ,
    "big band": GenreCategory.JAZZ,
    "latin jazz": GenreCategory.JAZZ,
    "acid jazz": GenreCategory.JAZZ,
    "nu-jazz": GenreCategory.JAZZ,
    # Classical
    "classical": GenreCategory.CLASSICAL,
    "baroque": GenreCategory.CLASSICAL,
    "romantic": GenreCategory.CLASSICAL,
    "contemporary classical": GenreCategory.CLASSICAL,
    "minimalism": GenreCategory.CLASSICAL,
    "opera": GenreCategory.CLASSICAL,
    "symphony": GenreCategory.CLASSICAL,
    "orchestral": GenreCategory.CLASSICAL,
    "chamber music": GenreCategory.CLASSICAL,
    "choral": GenreCategory.CLASSICAL,
    # Hip-hop
    "hip-hop": GenreCategory.HIP_HOP,
    "trap": GenreCategory.HIP_HOP,
    "boom bap": GenreCategory.HIP_HOP,
    "gangsta rap": GenreCategory.HIP_HOP,
    "conscious hip-hop": GenreCategory.HIP_HOP,
    "alternative hip-hop": GenreCategory.HIP_HOP,
    "underground hip-hop": GenreCategory.HIP_HOP,
    "east coast hip-hop": GenreCategory.HIP_HOP,
    "west coast hip-hop": GenreCategory.HIP_HOP,
    "southern hip-hop": GenreCategory.HIP_HOP,
    "crunk": GenreCategory.HIP_HOP,
    "grime": GenreCategory.HIP_HOP,
    # R&B
    "r&b": GenreCategory.RNB,
    "contemporary r&b": GenreCategory.RNB,
    "neo-soul": GenreCategory.RNB,
    "new jack swing": GenreCategory.RNB,
    # Country
    "country": GenreCategory.COUNTRY,
    "country rock": GenreCategory.COUNTRY,
    "outlaw country": GenreCategory.COUNTRY,
    "alt-country": GenreCategory.COUNTRY,
    "americana": GenreCategory.COUNTRY,
    "bluegrass": GenreCategory.COUNTRY,
    "honky tonk": GenreCategory.COUNTRY,
    # Folk
    "folk": GenreCategory.FOLK,
    "folk rock": GenreCategory.FOLK,
    "indie folk": GenreCategory.FOLK,
    "contemporary folk": GenreCategory.FOLK,
    "traditional folk": GenreCategory.FOLK,
    "singer-songwriter": GenreCategory.FOLK,
    # Blues
    "blues": GenreCategory.BLUES,
    "electric blues": GenreCategory.BLUES,
    "delta blues": GenreCategory.BLUES,
    "chicago blues": GenreCategory.BLUES,
    "blues rock": GenreCategory.BLUES,
    # Metal
    "metal": GenreCategory.METAL,
    "heavy metal": GenreCategory.METAL,
    "thrash metal": GenreCategory.METAL,
    "death metal": GenreCategory.METAL,
    "black metal": GenreCategory.METAL,
    "doom metal": GenreCategory.METAL,
    "power metal": GenreCategory.METAL,
    "progressive metal": GenreCategory.METAL,
    "nu-metal": GenreCategory.METAL,
    "metalcore": GenreCategory.METAL,
    "deathcore": GenreCategory.METAL,
    "symphonic metal": GenreCategory.METAL,
    # Punk
    "punk": GenreCategory.PUNK,
    "punk rock": GenreCategory.PUNK,
    "hardcore punk": GenreCategory.PUNK,
    "post-punk": GenreCategory.PUNK,
    "pop punk": GenreCategory.PUNK,
    "emo": GenreCategory.PUNK,
    "screamo": GenreCategory.PUNK,
    "ska punk": GenreCategory.PUNK,
    # Reggae
    "reggae": GenreCategory.REGGAE,
    "dub": GenreCategory.REGGAE,
    "ska": GenreCategory.REGGAE,
    "dancehall": GenreCategory.REGGAE,
    "roots reggae": GenreCategory.REGGAE,
    "rocksteady": GenreCategory.REGGAE,
    # Latin
    "latin": GenreCategory.LATIN,
    "salsa": GenreCategory.LATIN,
    "bachata": GenreCategory.LATIN,
    "merengue": GenreCategory.LATIN,
    "reggaeton": GenreCategory.LATIN,
    "bossa nova": GenreCategory.LATIN,
    "samba": GenreCategory.LATIN,
    "tango": GenreCategory.LATIN,
    "cumbia": GenreCategory.LATIN,
    "latin pop": GenreCategory.LATIN,
    # World
    "world": GenreCategory.WORLD,
    "afrobeat": GenreCategory.WORLD,
    "afropop": GenreCategory.WORLD,
    "celtic": GenreCategory.WORLD,
    "flamenco": GenreCategory.WORLD,
    "indian classical": GenreCategory.WORLD,
    "middle eastern": GenreCategory.WORLD,
    # Soul/Funk
    "soul": GenreCategory.SOUL,
    "motown": GenreCategory.SOUL,
    "northern soul": GenreCategory.SOUL,
    "funk": GenreCategory.FUNK,
    "p-funk": GenreCategory.FUNK,
    "disco": GenreCategory.FUNK,
    "nu-disco": GenreCategory.FUNK,
    # Ambient
    "ambient": GenreCategory.AMBIENT,
    "dark ambient": GenreCategory.AMBIENT,
    "drone": GenreCategory.AMBIENT,
    "new age": GenreCategory.AMBIENT,
    # Experimental
    "experimental": GenreCategory.EXPERIMENTAL,
    "avant-garde": GenreCategory.EXPERIMENTAL,
    "noise": GenreCategory.EXPERIMENTAL,
    "industrial": GenreCategory.EXPERIMENTAL,
    "post-rock": GenreCategory.EXPERIMENTAL,
    "math rock": GenreCategory.EXPERIMENTAL,
    "shoegaze": GenreCategory.EXPERIMENTAL,
    # Soundtrack
    "soundtrack": GenreCategory.SOUNDTRACK,
    "film score": GenreCategory.SOUNDTRACK,
    "video game music": GenreCategory.SOUNDTRACK,
    "anime soundtrack": GenreCategory.SOUNDTRACK,
}

# Source reliability weights
SOURCE_WEIGHTS: dict[str, float] = {
    "musicbrainz": 1.0,
    "discogs": 0.9,
    "lastfm": 0.7,
    "spotify": 0.8,
    "user": 0.5,
    "filename": 0.3,
}


def normalize_tag(raw_tag: str) -> str | None:
    """Normalize a single genre tag to its canonical form.

    Args:
        raw_tag: Raw tag string.

    Returns:
        Canonical tag name or None if not recognized.
    """
    # Clean and lowercase
    cleaned = raw_tag.strip().lower()

    # Direct lookup
    if cleaned in GENRE_ALIASES:
        return GENRE_ALIASES[cleaned]

    # Try without common suffixes/prefixes
    for suffix in [" music", " genre"]:
        if cleaned.endswith(suffix):
            base = cleaned[: -len(suffix)]
            if base in GENRE_ALIASES:
                return GENRE_ALIASES[base]

    return None


def get_category(canonical_tag: str) -> GenreCategory:
    """Get the category for a canonical tag.

    Args:
        canonical_tag: Canonical genre tag.

    Returns:
        Genre category.
    """
    return GENRE_CATEGORIES.get(canonical_tag, GenreCategory.OTHER)


def normalize_tags(
    raw_tags: list[str],
    source: str = "unknown",
) -> list[NormalizedTag]:
    """Normalize a list of genre tags.

    Args:
        raw_tags: List of raw tag strings.
        source: Source of the tags.

    Returns:
        List of normalized tags.
    """
    # Group by canonical name
    canonical_map: dict[str, NormalizedTag] = {}

    for raw in raw_tags:
        canonical = normalize_tag(raw)
        if canonical is None:
            continue

        if canonical in canonical_map:
            tag = canonical_map[canonical]
            if raw not in tag.raw_tags:
                tag.raw_tags.append(raw)
            if source not in tag.sources:
                tag.sources.append(source)
        else:
            category = get_category(canonical)
            canonical_map[canonical] = NormalizedTag(
                canonical=canonical,
                category=category,
                raw_tags=[raw],
                confidence=SOURCE_WEIGHTS.get(source, 0.5),
                sources=[source],
            )

    return list(canonical_map.values())


def merge_tags(
    tag_lists: list[tuple[list[str], str]],
) -> GenreResult:
    """Merge and normalize tags from multiple sources.

    Args:
        tag_lists: List of (tags, source) tuples.

    Returns:
        Merged and normalized genre result.
    """
    # Collect all raw tags
    all_raw: list[str] = []
    for tags, _ in tag_lists:
        all_raw.extend(tags)

    # Normalize each source
    canonical_map: dict[str, NormalizedTag] = {}

    for tags, source in tag_lists:
        normalized = normalize_tags(tags, source)
        source_weight = SOURCE_WEIGHTS.get(source, 0.5)

        for tag in normalized:
            if tag.canonical in canonical_map:
                existing = canonical_map[tag.canonical]
                # Merge raw tags
                for raw in tag.raw_tags:
                    if raw not in existing.raw_tags:
                        existing.raw_tags.append(raw)
                # Merge sources
                for src in tag.sources:
                    if src not in existing.sources:
                        existing.sources.append(src)
                # Update confidence based on source agreement
                existing.confidence = min(1.0, existing.confidence + source_weight * 0.3)
            else:
                canonical_map[tag.canonical] = tag

    # Sort by confidence
    all_tags = sorted(canonical_map.values(), key=lambda t: -t.confidence)

    # Calculate overall confidence based on source agreement
    num_sources = len(tag_lists)
    if num_sources > 1 and all_tags:
        # Higher confidence if multiple sources agree
        max_agreement = max(len(t.sources) for t in all_tags)
        overall_confidence = max_agreement / num_sources
    elif all_tags:
        overall_confidence = all_tags[0].confidence
    else:
        overall_confidence = 0.0

    # Determine primary and secondary
    primary = all_tags[0] if all_tags else None
    secondary = all_tags[1:4] if len(all_tags) > 1 else []

    return GenreResult(
        primary=primary,
        secondary=secondary,
        all_tags=all_tags,
        raw_tags=list(set(all_raw)),
        overall_confidence=overall_confidence,
    )


def suggest_genres(partial: str, limit: int = 10) -> list[str]:
    """Suggest genres matching a partial string.

    Args:
        partial: Partial genre string.
        limit: Maximum suggestions to return.

    Returns:
        List of matching canonical genre names.
    """
    partial_lower = partial.lower()
    matches: set[str] = set()

    # Search aliases
    for alias, canonical in GENRE_ALIASES.items():
        if partial_lower in alias:
            matches.add(canonical)
            if len(matches) >= limit:
                break

    return sorted(matches)[:limit]


def get_all_genres() -> list[str]:
    """Get all canonical genre names.

    Returns:
        Sorted list of all canonical genres.
    """
    return sorted(set(GENRE_ALIASES.values()))


def get_genres_by_category(category: GenreCategory) -> list[str]:
    """Get all genres in a category.

    Args:
        category: Genre category.

    Returns:
        List of canonical genre names in the category.
    """
    return sorted(
        canonical for canonical, cat in GENRE_CATEGORIES.items() if cat == category
    )


class GenreNormalizer:
    """Genre normalization service.

    This class provides a convenient interface for genre normalization
    with caching and batch operations.

    Example:
        normalizer = GenreNormalizer()

        # Single tag
        tag = normalizer.normalize("hip hop")

        # Multiple sources
        result = normalizer.normalize_from_sources({
            "musicbrainz": ["hip hop", "rap"],
            "discogs": ["hip-hop", "urban"],
        })
    """

    def __init__(self) -> None:
        """Initialize the normalizer."""
        self._cache: dict[str, str | None] = {}

    def normalize(self, raw_tag: str) -> NormalizedTag | None:
        """Normalize a single tag.

        Args:
            raw_tag: Raw tag string.

        Returns:
            Normalized tag or None.
        """
        # Check cache
        if raw_tag in self._cache:
            canonical = self._cache[raw_tag]
            if canonical is None:
                return None
            return NormalizedTag(
                canonical=canonical,
                category=get_category(canonical),
                raw_tags=[raw_tag],
            )

        # Normalize
        canonical = normalize_tag(raw_tag)
        self._cache[raw_tag] = canonical

        if canonical is None:
            return None

        return NormalizedTag(
            canonical=canonical,
            category=get_category(canonical),
            raw_tags=[raw_tag],
        )

    def normalize_batch(self, raw_tags: list[str]) -> list[NormalizedTag]:
        """Normalize multiple tags.

        Args:
            raw_tags: List of raw tags.

        Returns:
            List of normalized tags.
        """
        results = []
        for raw in raw_tags:
            normalized = self.normalize(raw)
            if normalized:
                results.append(normalized)
        return results

    def normalize_from_sources(
        self,
        sources: dict[str, list[str]],
    ) -> GenreResult:
        """Normalize tags from multiple sources.

        Args:
            sources: Dictionary mapping source name to tag list.

        Returns:
            Merged genre result.
        """
        tag_lists = [(tags, source) for source, tags in sources.items()]
        return merge_tags(tag_lists)

    def clear_cache(self) -> None:
        """Clear the normalization cache."""
        self._cache.clear()
