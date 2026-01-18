# MIDI Pattern Extractor

Analyze MIDI files to extract reusable musical patterns for generative music systems.

## Features

- **MIDI Ingest & Normalization** — Parse MIDI files with tempo/time-sig mapping
- **Track Role Inference** — Automatically classify tracks (drums, bass, chords, lead, arp, pad)
- **Pattern Extraction** — Extract rhythmic and melodic patterns with fingerprinting
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

## CLI Usage

```bash
# Analyze a single MIDI file
midi-analyzer analyze song.mid

# Analyze a directory of MIDI files  
midi-analyzer analyze ./midi-corpus/ --recursive

# --- Clip Library Commands ---

# Index MIDI files into the library
midi-analyzer library index ./midi-corpus/ -r --genre jazz --artist "Various"

# Query clips by role and genre
midi-analyzer library query --role bass --genre jazz

# Query clips by artist
midi-analyzer library query --artist "Miles Davis"

# Export a clip to MIDI
midi-analyzer library export abc123_0 -o bass_clip.mid --tempo 120

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
