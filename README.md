# MIDI Pattern Extractor

Analyze MIDI files to extract reusable musical patterns for generative music systems.

## Features

- **MIDI Ingest & Normalization** — Parse MIDI files with tempo/time-sig mapping
- **Track Role Inference** — Automatically classify tracks (drums, bass, chords, lead, arp, pad)
- **Pattern Extraction** — Extract rhythmic and melodic patterns with fingerprinting
- **Arpeggio Inference** — Detect arpeggio patterns with rate, intervals, octave jumps, and gate
- **Section Segmentation** — Detect song structure (intro, verse, chorus, etc.) using novelty analysis
- **Harmony Analysis** — Key detection (Krumhansl-Schmuckler) and chord progression inference
- **Genre Tagging** — Retrieve genre/tags via MusicBrainz, with canonical taxonomy normalization
- **Clip Library** — Index and query tracks by genre, artist, and instrument role
- **MIDI Export** — Export individual tracks or clips to MIDI files
- **MIDI Playback** — Play tracks with auto-instrument selection based on track role
- **Batch Processing** — Process large collections with parallel workers and checkpointing

## Installation

```bash
# Clone the repository
git clone https://github.com/gramster/midi-analyzer.git
cd midi-analyzer

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows

# Install in development mode
pip install -e ".[dev]"

# Install with player support (optional)
pip install -e ".[player]"
```

## Quick Start

### Analyze a MIDI File

```python
from midi_analyzer.ingest import parse_midi_file
from midi_analyzer.harmony import detect_key, detect_chords

# Parse a MIDI file
song = parse_midi_file("song.mid")

# Detect key and chord progression
key = detect_key(song)
print(f"Key: {key.key.name} {key.mode.value}")

chords = detect_chords(song)
print(f"Chords: {' → '.join(c.chord.symbol for c in chords.events[:8])}")
```

### Build and Query a Clip Library

```python
from midi_analyzer.library import ClipLibrary, ClipQuery
from midi_analyzer.models.core import TrackRole
from midi_analyzer.export import export_track

# Create/open a library
library = ClipLibrary("my_library.db")

# Index MIDI files with metadata
library.index_directory(
    "/path/to/midi/collection",
    genres=["jazz", "fusion"],
    artist="Various Artists",
)

# Query for bass tracks from jazz songs
clips = library.query(ClipQuery(
    role=TrackRole.BASS,
    genre="jazz",
    limit=10,
))

# Export a clip to MIDI
for clip in clips:
    track = library.load_track(clip)
    export_track(track, f"bass_{clip.clip_id}.mid", tempo_bpm=120)
```

### Play MIDI Clips

```python
from midi_analyzer.player import MidiPlayer, PlaybackOptions, get_instrument_name
from midi_analyzer.analysis import classify_track_role

# Play a track with auto-instrument based on role
with MidiPlayer() as player:
    role = classify_track_role(track)
    print(f"Playing {role.name} track")
    player.play_track(track, PlaybackOptions(tempo_bpm=120))

# List available MIDI devices
from midi_analyzer.player import list_midi_devices
for device_id, name, is_output in list_midi_devices():
    if is_output:
        print(f"  [{device_id}] {name}")
```

### Normalize Genre Tags

```python
from midi_analyzer.metadata.genres import GenreNormalizer

normalizer = GenreNormalizer()

# Normalize tags from multiple sources
result = normalizer.normalize_from_sources({
    "musicbrainz": ["hip hop", "rap", "urban"],
    "user": ["hip-hop"],
})

print(f"Primary genre: {result.primary.canonical}")  # "hip-hop"
print(f"Confidence: {result.overall_confidence}")
```

### Analyze Song Structure

```python
from midi_analyzer.ingest import parse_midi_file
from midi_analyzer.analysis.sections import analyze_sections, SectionType

# Parse and analyze structure
song = parse_midi_file("song.mid")
analysis = analyze_sections(song)

# Show form sequence (A, B, A, C, etc.)
print(f"Form: {' → '.join(analysis.form_sequence)}")

# Iterate through sections
for section in analysis.sections:
    print(f"Section {section.form_label}: bars {section.start_bar}-{section.end_bar}")
    if section.type_hint != SectionType.UNKNOWN:
        print(f"  Type: {section.type_hint.value} ({section.type_confidence:.0%})")
```

### Extract Arpeggio Patterns

```python
from midi_analyzer.ingest import parse_midi_file
from midi_analyzer.analysis import classify_track_role
from midi_analyzer.analysis.arpeggios import analyze_arp_track

song = parse_midi_file("song.mid")

for track in song.tracks:
    role = classify_track_role(track)
    if role.arp > 0.5:  # Track likely an arpeggio
        analysis = analyze_arp_track(track, song)
        print(f"Track: {track.name}")
        print(f"  Rate: {analysis.dominant_rate}")
        print(f"  Gate: {analysis.avg_gate:.2f}")
        for pattern in analysis.patterns[:3]:
            print(f"  Pattern: intervals={pattern.interval_sequence[:4]}, "
                  f"octaves={pattern.octave_jumps[:4]}")
```

## CLI Usage

```bash
# Analyze a single MIDI file
midi-analyzer analyze song.mid

# Analyze with verbose output
midi-analyzer analyze song.mid -v

# Analyze with section structure detection
midi-analyzer analyze song.mid --sections

# Analyze with arpeggio pattern extraction
midi-analyzer analyze song.mid --arpeggios

# Analyze a directory of MIDI files  
midi-analyzer analyze ./midi-corpus/ --recursive

# --- Song Structure Analysis ---

# Detect song sections (intro, verse, chorus, etc.)
midi-analyzer structure song.mid

# Output as JSON for programmatic use
midi-analyzer structure song.mid --format json

# Verbose mode shows per-bar feature details
midi-analyzer structure song.mid -v

# --- Arpeggio Pattern Extraction ---

# Extract arpeggios from tracks
midi-analyzer arpeggios song.mid

# Analyze a specific track
midi-analyzer arpeggios song.mid --track 2

# Output as JSON
midi-analyzer arpeggios song.mid --format json

# --- Clip Library Commands ---

# Index MIDI files into the library
midi-analyzer library index ./midi-corpus/ -r --genre jazz --artist "Various"

# Query clips by role and genre
midi-analyzer library query --role bass --genre jazz

# Query clips by artist
midi-analyzer library query --artist "Miles Davis"

# Export a clip to MIDI
midi-analyzer library export abc123_0 -o bass_clip.mid --tempo 120

# Enrich library with MusicBrainz genre tags
midi-analyzer library enrich

# View library statistics
midi-analyzer library stats

# List all genres in library
midi-analyzer library list-genres

# List all artists
midi-analyzer library list-artists

# --- Quick Commands ---

# Search patterns (shortcut for library query)
midi-analyzer search --role drums --genre rock

# Export a pattern
midi-analyzer export abc123_0 --format midi -o output.mid

# Show statistics
midi-analyzer stats

# --- Playback Commands ---

# Play a MIDI file
midi-analyzer play song.mid

# Play a clip from the library
midi-analyzer play abc123_0

# Play with options
midi-analyzer play song.mid --tempo 140 --transpose -2 --loop

# List MIDI output devices
midi-analyzer list-devices
```

## Python API Reference

### Core Modules

| Module | Purpose |
|--------|---------|
| `midi_analyzer.ingest` | Parse MIDI files, extract metadata |
| `midi_analyzer.analysis` | Track role classification, feature extraction |
| `midi_analyzer.analysis.arpeggios` | Arpeggio pattern detection and extraction |
| `midi_analyzer.analysis.sections` | Song structure segmentation |
| `midi_analyzer.harmony` | Key detection, chord progression inference |
| `midi_analyzer.metadata` | MusicBrainz integration, genre normalization |
| `midi_analyzer.library` | Clip indexing and querying |
| `midi_analyzer.export` | MIDI file export |
| `midi_analyzer.player` | MIDI playback with role-based instruments |
| `midi_analyzer.storage` | SQLite repository, search |
| `midi_analyzer.processing` | Batch processing |

### Key Classes

```python
# Parsing
from midi_analyzer.ingest import parse_midi_file, MidiParser

# Analysis  
from midi_analyzer.analysis import classify_track_role, extract_features

# Arpeggio Analysis
from midi_analyzer.analysis.arpeggios import ArpAnalyzer, analyze_arp_track, extract_arp_patterns

# Section Analysis
from midi_analyzer.analysis.sections import SectionAnalyzer, analyze_sections, SectionType

# Harmony
from midi_analyzer.harmony import detect_key, detect_chords

# Library
from midi_analyzer.library import ClipLibrary, ClipQuery, ClipInfo

# Export
from midi_analyzer.export import export_track, export_tracks, extract_clip

# Playback
from midi_analyzer.player import MidiPlayer, PlaybackOptions, list_midi_devices

# Metadata
from midi_analyzer.metadata import GenreNormalizer, search_recording
```

## Development

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=src/midi_analyzer

# Run linter
ruff check src/ tests/

# Run type checker  
mypy src/
```

## Architecture

See [MIDI_Pattern_Extractor_Spec.md](MIDI_Pattern_Extractor_Spec.md) for detailed architecture documentation.

## License

MIT
