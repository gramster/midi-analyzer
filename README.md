# MIDI Pattern Extractor

Analyze MIDI files to extract reusable musical patterns for generative music systems.

## Features

- **MIDI Ingest & Normalization** — Parse MIDI files with tempo/time-sig mapping
- **Track Role Inference** — Automatically classify tracks (drums, bass, chords, lead, arp, pad)
- **Pattern Extraction** — Extract rhythmic and melodic patterns with fingerprinting
- **Harmony Analysis** — Key detection and chord progression inference
- **Genre Tagging** — Retrieve genre/tags via MusicBrainz and Discogs APIs
- **Pattern Library** — SQLite-based searchable pattern corpus

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
```

## Usage

```bash
# Analyze a single MIDI file
midi-analyzer analyze song.mid

# Analyze a directory of MIDI files
midi-analyzer analyze ./midi-corpus/ --recursive

# Search patterns
midi-analyzer search --role drums --meter 4/4

# Export statistics
midi-analyzer stats
```

## Development

```bash
# Run tests
pytest

# Run linter
ruff check src/ tests/

# Run type checker
mypy src/
```

## Architecture

See [MIDI_Pattern_Extractor_Spec.md](MIDI_Pattern_Extractor_Spec.md) for detailed architecture documentation.

## License

MIT
