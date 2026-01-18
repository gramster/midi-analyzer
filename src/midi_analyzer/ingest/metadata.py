"""Metadata extraction from MIDI files and filenames."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import mido

from midi_analyzer.ingest.nonstop2k_artists import NONSTOP2K_ARTISTS
from midi_analyzer.models.core import SongMetadata

if TYPE_CHECKING:
    pass


class MetadataExtractor:
    """Extract metadata from MIDI files and their paths.

    Supports multiple filename formats and folder structures:
    - Folder structure: {Letter}/{Artist}/{Title}.mid
    - Hyphenated: {Artist} - {Title}.mid
    - nonstop2k format: artist-song-title-timestamp-domain.mid
    - MIDI file metadata (track names, copyright, text events)
    """

    # Common domain suffixes to strip
    DOMAIN_SUFFIXES = [
        "nonstop2k.com",
        "midi-karaoke.info",
        "freemidi.org",
        "midiworld.com",
    ]

    # Timestamp patterns (8+ digits)
    TIMESTAMP_PATTERN = re.compile(r"\d{8,}")

    # Common separator patterns
    SEPARATORS = [" - ", " – ", " — ", "_-_", "__"]

    def extract(self, file_path: Path | str, midi_file: mido.MidiFile | None = None) -> SongMetadata:
        """Extract metadata from a MIDI file.

        Tries multiple strategies in order of reliability:
        1. MIDI file metadata (if available)
        2. Folder structure
        3. Filename parsing

        Args:
            file_path: Path to the MIDI file.
            midi_file: Optional pre-loaded mido.MidiFile object.

        Returns:
            SongMetadata with extracted information.
        """
        file_path = Path(file_path)

        # Try to extract from MIDI metadata first
        midi_metadata = self._extract_from_midi(midi_file) if midi_file else SongMetadata()

        # Try folder structure
        folder_metadata = self._extract_from_folder_structure(file_path)

        # Try filename
        filename_metadata = self._extract_from_filename(file_path)

        # Merge results, preferring more reliable sources
        return self._merge_metadata(midi_metadata, folder_metadata, filename_metadata)

    def _extract_from_midi(self, midi_file: mido.MidiFile) -> SongMetadata:
        """Extract metadata from MIDI file events."""
        artist = ""
        title = ""
        copyright_text = ""
        text_events: list[str] = []

        for track in midi_file.tracks:
            for msg in track:
                if msg.type == "track_name" and not title:
                    # First track name often contains the title
                    title = msg.name
                elif msg.type == "copyright":
                    copyright_text = msg.text
                elif msg.type == "text":
                    text_events.append(msg.text)

        # Try to extract artist from copyright or text events
        if copyright_text:
            # Copyright often contains artist info
            artist = self._extract_artist_from_copyright(copyright_text)

        return SongMetadata(
            artist=artist,
            title=title,
            source="midi_metadata" if (artist or title) else "unknown",
            confidence=0.7 if title else 0.0,
        )

    def _extract_artist_from_copyright(self, copyright_text: str) -> str:
        """Try to extract artist name from copyright text."""
        # Common patterns: "© 2020 Artist Name", "Copyright Artist Name"
        patterns = [
            r"©\s*\d{4}\s+(.+)",
            r"[Cc]opyright\s+(?:\d{4}\s+)?(.+)",
            r"by\s+(.+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, copyright_text)
            if match:
                return match.group(1).strip()

        return ""

    def _extract_from_folder_structure(self, file_path: Path) -> SongMetadata:
        """Extract metadata from folder structure.

        Supports: {Letter}/{Artist}/{Title}.mid
        """
        parts = file_path.parts

        # Need at least: Letter / Artist / filename
        if len(parts) < 3:
            return SongMetadata()

        filename = file_path.stem
        parent = parts[-2]
        grandparent = parts[-3] if len(parts) >= 3 else ""

        # Check if grandparent is a single letter (A-Z)
        if len(grandparent) == 1 and grandparent.isalpha():
            # This looks like Letter/Artist/Song structure
            artist = parent
            title = self._clean_title(filename)

            return SongMetadata(
                artist=artist,
                title=title,
                source="folder_structure",
                confidence=0.8,
            )

        return SongMetadata()

    def _extract_from_filename(self, file_path: Path) -> SongMetadata:
        """Extract metadata from filename."""
        filename = file_path.stem

        # Clean up the filename
        cleaned = self._clean_filename(filename)

        # Try different parsing strategies
        for strategy in [
            self._parse_separator_format,
            self._parse_nonstop2k_format,
            self._parse_hyphenated_words,
        ]:
            result = strategy(cleaned)
            if result.artist or result.title:
                return result

        # Fallback: use whole filename as title
        return SongMetadata(
            title=self._clean_title(cleaned),
            source="filename_fallback",
            confidence=0.3,
        )

    def _clean_filename(self, filename: str) -> str:
        """Clean up a filename by removing common suffixes and noise."""
        result = filename

        # Remove domain suffixes
        for domain in self.DOMAIN_SUFFIXES:
            result = result.replace(domain, "")

        # Remove timestamps
        result = self.TIMESTAMP_PATTERN.sub("", result)

        # Remove trailing/leading separators and whitespace
        result = result.strip("-_ ")

        return result

    def _clean_title(self, title: str) -> str:
        """Clean up a title string."""
        # Replace underscores and hyphens with spaces
        result = title.replace("_", " ").replace("-", " ")

        # Remove multiple spaces
        result = re.sub(r"\s+", " ", result)

        # Title case
        result = result.strip().title()

        return result

    def _parse_separator_format(self, filename: str) -> SongMetadata:
        """Parse 'Artist - Title' format."""
        for sep in self.SEPARATORS:
            if sep in filename:
                parts = filename.split(sep, 1)
                if len(parts) == 2:
                    artist = self._clean_title(parts[0])
                    title = self._clean_title(parts[1])

                    return SongMetadata(
                        artist=artist,
                        title=title,
                        source="filename_separator",
                        confidence=0.6,
                    )

        return SongMetadata()

    def _parse_nonstop2k_format(self, filename: str) -> SongMetadata:
        """Parse nonstop2k format using known artist database.

        Uses the NONSTOP2K_ARTISTS database to find the longest matching
        artist name prefix, then treats the remainder as the title.
        
        Example: adriatique-whomadewho-miracle -> "Adriatique" + "Whomadewho" / "Miracle"
        """
        # Split on hyphens - keep all parts for artist matching
        all_parts = filename.lower().split("-")

        if len(all_parts) < 2:
            return SongMetadata()

        # Try to find known artists by matching prefixes
        # Check for multiple artists (collaborations)
        found_artists: list[str] = []
        remaining_parts = all_parts[:]
        
        while remaining_parts:
            # Try progressively shorter prefixes to find an artist match
            matched = False
            for end_idx in range(len(remaining_parts), 0, -1):
                candidate_slug = "-".join(remaining_parts[:end_idx])
                if candidate_slug in NONSTOP2K_ARTISTS:
                    found_artists.append(NONSTOP2K_ARTISTS[candidate_slug])
                    remaining_parts = remaining_parts[end_idx:]
                    matched = True
                    break
            
            if not matched:
                # No more artists found, rest is title
                break

        # Filter numeric-only parts from remaining (title) parts
        title_parts = [p for p in remaining_parts if not p.isdigit()]

        if found_artists and title_parts:
            # Found at least one artist and have title remaining
            artist = ", ".join(found_artists)
            title = " ".join(title_parts).title()
            
            return SongMetadata(
                artist=artist,
                title=title,
                source="filename_nonstop2k",
                confidence=0.8,  # High confidence with known artists
            )
        elif found_artists:
            # Found artists but no title - unusual, low confidence
            artist = ", ".join(found_artists)
            return SongMetadata(
                artist=artist,
                title="",
                source="filename_nonstop2k",
                confidence=0.3,
            )
        
        # No known artists found - fall back to heuristic
        # Filter numeric parts for heuristic fallback
        parts = [p for p in all_parts if not p.isdigit()]
        
        if len(parts) < 3:
            return SongMetadata()

        # For 3 parts: first 2 are artist, last 1 is title
        if len(parts) == 3:
            title_start = 2
        else:
            # For 4+, use middle point
            title_start = len(parts) // 2

        artist_parts = parts[:title_start]
        title_parts = parts[title_start:]

        artist = " ".join(artist_parts).title()
        title = " ".join(title_parts).title()

        return SongMetadata(
            artist=artist,
            title=title,
            source="filename_nonstop2k_heuristic",
            confidence=0.4,
        )

    def _parse_hyphenated_words(self, filename: str) -> SongMetadata:
        """Parse hyphen-separated words as a title (no artist)."""
        if "-" in filename:
            title = filename.replace("-", " ").title()
            return SongMetadata(
                title=title,
                source="filename_hyphenated",
                confidence=0.3,
            )

        return SongMetadata()

    def _merge_metadata(
        self,
        midi_meta: SongMetadata,
        folder_meta: SongMetadata,
        filename_meta: SongMetadata,
    ) -> SongMetadata:
        """Merge metadata from multiple sources, preferring higher confidence."""
        # Sort by confidence
        sources = sorted(
            [midi_meta, folder_meta, filename_meta],
            key=lambda m: m.confidence,
            reverse=True,
        )

        # Take best values
        artist = ""
        title = ""
        source = "unknown"
        confidence = 0.0

        for meta in sources:
            if not artist and meta.artist:
                artist = meta.artist
            if not title and meta.title:
                title = meta.title
            if meta.confidence > confidence:
                confidence = meta.confidence
                source = meta.source

        return SongMetadata(
            artist=artist,
            title=title,
            source=source,
            confidence=confidence,
        )


def extract_metadata(file_path: Path | str, midi_file: mido.MidiFile | None = None) -> SongMetadata:
    """Convenience function to extract metadata from a MIDI file.

    Args:
        file_path: Path to the MIDI file.
        midi_file: Optional pre-loaded MIDI file object.

    Returns:
        SongMetadata with extracted information.
    """
    extractor = MetadataExtractor()
    return extractor.extract(file_path, midi_file)
