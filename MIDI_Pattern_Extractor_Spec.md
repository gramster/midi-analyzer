# MIDI Pattern Extractor — Analysis Architecture (v1)

This document describes a system that  *analyzes existing MIDI files* to extract reusable musical structures.

The output is a **pattern corpus** that can later drive groove templates, chord timelines, and arpeggiator presets.

---

## 1. Goals

- Dissect MIDI songs into **reusable musical patterns**
- Use song title and artists to perform a web search and attempt to retrieve genre information and
descriptive tags
- Infer **track roles** (drums, bass, chords, lead, arp, pad)
- Extract **rhythmic, melodic, harmonic, and arpeggiated motifs**
- Build a searchable **pattern library** indexed by role, meter, density, harmony, genre, tags
- Keep the system modular, deterministic, and explainable (no black-box ML in v1)

---

## 2. High-Level Architecture

```
MIDI Files
   │
   ▼
MIDI Ingest & Normalization
   │
   ├─▶ Track Analyzer (per-track)
   │       ├─ Feature Extraction
   │       ├─ Role Inference
   │       ├─ Pattern Chunking
   │       └─ Pattern Mining
   │
   └─▶ Song Analyzer (cross-track)
           ├─ Key / Scale Detection
           ├─ Chord Progression Inference
           ├─ Arpeggio Inference
           └─ Section Segmentation
   │
   ▼
Pattern Library (SQLite / JSON)
   │
   ▼
Arpestrator Rehydration
```

---

## 3. Pipeline Stages

### Stage 0 — MIDI Ingest & Normalization

**Inputs**
- MIDI note on/off events
- Tempo map
- Time signature map

**Outputs**
- Normalized `NoteEvent` objects:
  - `startBeat`, `durationBeats`
  - `pitch`, `velocity`
  - `trackId`, `channel`
- Bar and beat indices
- Quantized timing lane (e.g. 1/16 grid) alongside raw timing
- Artist, Genre, Tags

Purpose:
- Preserve expressive timing
- Enable grid-based comparison and hashing

Notes:
   - Many songs come from a website which uses file name formats similar to this example:

       le-youth-jerro-lizzy-land-lost-20230130024203-nonstop2k.com

    The artist in this case is "Le Youth ft Lizzy" and the title is "Land Lost". 

    In many other cases the files will be in subfolders based on the artist, which in turn 
    are in subfolders based on the first letter of the artists name; e.g.

    R/Ramones/I wanna be sedated.mid

    Heuristics will be needed to extract artist/title in other cases. There may be metadata in the 
    MIDI files that cann be used.


---

### Stage 1 — Track Feature Extraction

Computed per track:

- Note density (onsets per bar)
- Polyphony ratio
- Pitch range and median pitch
- Rhythmic complexity (syncopation score)
- Repetition score
- Drum-likeness indicators (channel 10, short notes, pitch-class entropy)

These features are stored for later classification and pattern tagging.

---

### Stage 2 — Track Role Inference

Each track is scored against role heuristics:

| Role | Key Indicators |
|-----|---------------|
| Drums | Channel 10, high density, short notes, unpitched feel |
| Bass | Low register, mostly monophonic, downbeat-heavy |
| Chords / Pad | Polyphonic, long durations, mid register |
| Lead | Monophonic, wide pitch movement, phrase-like |
| Arp | High note rate, broken-chord intervals, repetition |

Output:
- `role_probs = {drums, bass, chords, lead, arp, pad, other}`

Roles are probabilistic, not exclusive.

---

### Stage 3 — Bar Chunking & Fingerprinting

Tracks are segmented into:
- 1-bar, 2-bar, and 4-bar chunks

For each chunk compute:

**Rhythm fingerprint**
- Binary or weighted onset grid (e.g. 16 or 32 steps)

**Pitch fingerprint**
- Relative interval sequence (normalized for transposition)

**Combined fingerprint**
- Hash of rhythm + pitch signatures

**Shape descriptors**
- Density
- Accent profile
- Pitch contour

These fingerprints enable fast deduplication and similarity search.

---

### Stage 4 — Pattern Mining & Deduplication

- Detect repeated chunks within a track
- Cluster similar chunks across tracks and files
- Select canonical representatives
- Record instances with confidence scores

Result:
- A library of reusable rhythmic and melodic patterns.

---

### Stage 5 — Key & Harmony Inference (Song-Level)

**Key detection**
- Pitch-class histograms (long notes weighted higher)
- Stability checks across sections

**Chord progression inference**
- Sliding windows (beat or half-bar)
- Candidate triads / 7ths
- Penalize unstable or non-diatonic chords
- Temporal smoothing to reduce jitter

**Roman numeral mapping**
- Relative to detected key
- Confidence annotated per segment

---

### Stage 6 — Arpeggio Inference

For tracks with high `arp` probability:

- Group notes into chord windows
- Infer underlying chord per window
- Extract traversal signature:
  - interval order
  - octave jumps
  - rate and gate feel

Output:
- Arp descriptors directly mappable to Arpestrator parameters.

---

### Stage 7 — Section Segmentation

Rather than forcing labels (verse/chorus):

- Compute per-bar feature vectors:
  - active track count
  - density per role
  - harmonic rhythm
- Detect novelty peaks → section boundaries
- Cluster sections into A/B/C forms

Optional later labeling:
- Verse / Chorus / Breakdown (heuristic + confidence)

---

## 4. Pattern Library Schema (Minimal)

### Songs
- `song_id`
- `source_path`
- `tempo_map_json`
- `time_sig_map_json`
- `detected_key`
- `detected_mode`
- `tags_json`
- `artist`
- `title`
- `genre`
- `tags`

### Tracks
- `track_id`
- `song_id`
- `name`
- `role_probs_json`
- `features_json`

### Patterns
- `pattern_id`
- `role`
- `length_bars`
- `meter`
- `grid_resolution`
- `rhythm_fp`
- `pitch_fp`
- `combo_fp`
- `representation_json`
- `stats_json`
- `tags_json`

### Pattern Instances
- `pattern_id`
- `song_id`
- `track_id`
- `start_bar`
- `confidence`
- `transform_json`

---

## 5. Pattern Representations

### Drum Pattern (example)
```json
{
  "stepsPerBar": 16,
  "hits": [
    {"step": 0, "pitch": 36, "vel": 110},
    {"step": 8, "pitch": 38, "vel": 95}
  ]
}
```

### Melodic Pattern (example)
```json
{
  "events": [
    {"step": 0, "interval": 0, "dur": 2},
    {"step": 2, "interval": 3, "dur": 2},
    {"step": 4, "interval": -2, "dur": 4}
  ]
}
```

### Arp Pattern (example)
```json
{
  "rate": "1/16",
  "interval_sequence": [0, 7, 12, 7],
  "octave_jumps": [0, 0, 1, 0]
}
```

---

## 6. Metadata & Genre Retrieval

### Metadata Extraction Strategy

**Priority order for artist/title extraction:**

1. **MIDI file metadata** — Check standard MIDI meta events:
   - Track name (meta event 0x03)
   - Copyright notice (meta event 0x02)
   - Text events (meta event 0x01)

2. **Folder structure parsing** — Common patterns:
   - `{Letter}/{Artist}/{Title}.mid`
   - `{Artist} - {Title}.mid`
   - `{Title} - {Artist}.mid`

3. **Filename heuristics** — For sites like nonstop2k:
   - Split on hyphens
   - Remove timestamps (8+ digit sequences)
   - Remove domain suffixes
   - Use word capitalization and common patterns

### Genre & Tag Retrieval

**Web search strategy:**

1. **MusicBrainz API** (preferred — structured, no API key required for basic use):
   - Search recordings by artist + title
   - Retrieve genre tags, release info, related artists
   - Rate limit: 1 request/second

2. **Discogs API** (fallback — requires free API key):
   - Search releases by artist + title
   - Rich genre/style taxonomy
   - Rate limit: 60 requests/minute

3. **Last.fm API** (supplementary — free API key):
   - Track tags (crowdsourced)
   - Similar tracks/artists for clustering
   - Rate limit: 5 requests/second

**Tag normalization:**
- Map vendor-specific tags to canonical genre taxonomy
- Store both raw tags and normalized categories
- Confidence scoring based on source agreement

**Caching:**
- Cache API responses to avoid repeated lookups
- Store in SQLite alongside pattern data
- Exponential backoff on rate limits

---

## 7. MVP Scope Recommendation

**Ship first (Phase 1):**
- Project scaffolding (Python package, CLI, tests)
- MIDI ingest + normalization
- Basic metadata extraction from filenames/folders
- Track feature extraction
- Track role inference

**Phase 2:**
- 1-bar and 2-bar pattern extraction
- Pattern fingerprinting
- Deduplication within songs
- SQLite pattern library

**Phase 3:**
- Genre/tag retrieval via web APIs
- Cross-song pattern clustering
- Key & chord detection
- Pattern search/query interface

**Defer to v2:**
- Section labeling
- Full arpeggio inference
- Arpestrator export formats

---

## 8. Technical Stack

**Core:**
- Python 3.11+
- `mido` — MIDI file parsing
- `music21` — Music theory utilities (optional, for chord analysis)
- SQLite — Pattern storage
- Click — CLI interface

**Web APIs:**
- `musicbrainzngs` — MusicBrainz client
- `httpx` — Async HTTP for API calls
- `tenacity` — Retry logic with backoff

**Testing:**
- pytest
- pytest-cov

---

## 9. Relationship to Arpestrator

This system provides:
- Groove templates → Groove Pattern nodes
- Accent maps → Velocity Pattern nodes
- Rhythm masks → Rhythmic Filter patterns
- Chord timelines → Chord Progression nodes
- Arp descriptors → Arpeggiator presets

Together, they form a closed loop:

**analyze → extract → generate → evolve**

