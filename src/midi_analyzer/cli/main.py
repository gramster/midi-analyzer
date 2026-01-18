"""Main CLI entry point for MIDI Analyzer."""

from __future__ import annotations

import json
from pathlib import Path

import click

from midi_analyzer import __version__
from midi_analyzer.models.core import TrackRole


# ANSI color codes for terminal output
class Colors:
    """ANSI color codes for styled terminal output."""

    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    END = "\033[0m"


def color(text: str, *codes: str) -> str:
    """Apply color codes to text."""
    return "".join(codes) + str(text) + Colors.END


@click.group()
@click.version_option(version=__version__, prog_name="midi-analyzer")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output.")
@click.option(
    "-c",
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to configuration file.",
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool, config: Path | None) -> None:
    """MIDI Pattern Extractor - Analyze MIDI files to extract reusable patterns."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["config"] = config


# Default library database path
DEFAULT_LIBRARY = Path("midi_library.db")


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-r",
    "--recursive",
    is_flag=True,
    help="Recursively process directories.",
)
@click.option("-v", "--verbose", is_flag=True, help="Show detailed analysis output.")
@click.option("--sections", is_flag=True, help="Include section structure analysis.")
@click.option("--arpeggios", is_flag=True, help="Include arpeggio pattern analysis.")
@click.pass_context
def analyze(
    ctx: click.Context,
    path: Path,
    recursive: bool,
    verbose: bool,
    sections: bool,
    arpeggios: bool,
) -> None:
    """Analyze MIDI files and display results.

    PATH can be a single MIDI file or a directory containing MIDI files.
    
    Use --sections to detect song structure (intro, verse, chorus, etc.).
    Use --arpeggios to extract arpeggio patterns from tracks.
    
    To index files into a searchable database, use 'library index' instead.
    """
    # Use command-level verbose or parent-level verbose
    verbose = verbose or ctx.obj.get("verbose", False)

    if path.is_file():
        files = [path]
    else:
        pattern = "**/*.mid" if recursive else "*.mid"
        files = list(path.glob(pattern))
        # Also include .midi extension
        files.extend(path.glob(pattern.replace(".mid", ".midi")))

    if not files:
        click.echo(f"No MIDI files found in {path}", err=True)
        raise SystemExit(1)

    click.echo(f"Found {len(files)} MIDI file(s) to analyze")

    if verbose:
        for f in files[:10]:
            click.echo(f"  - {f}")
        if len(files) > 10:
            click.echo(f"  ... and {len(files) - 10} more")

    # Analyze files
    from midi_analyzer.ingest import parse_midi_file
    from midi_analyzer.harmony import detect_key_for_song, detect_chord_progression_for_song
    from midi_analyzer.analysis import classify_track_role, FeatureExtractor
    from midi_analyzer.analysis.sections import analyze_sections, SectionType
    from midi_analyzer.analysis.arpeggios import analyze_arp_track

    feature_extractor = FeatureExtractor()
    success_count = 0
    failed_files: list[tuple[Path, str]] = []

    for file_path in files:
        try:
            song = parse_midi_file(file_path)
            key = detect_key_for_song(song)

            # Basic summary line
            click.echo(f"\n{color(file_path.name, Colors.BOLD, Colors.CYAN)}: {key.root_name} {key.mode.value} ({len(song.tracks)} tracks)")

            if verbose:
                # Show timing info
                click.echo(f"  Tempo: {song.primary_tempo:.1f} BPM, Time sig: {song.primary_time_sig}")
                click.echo(f"  Duration: {song.total_beats:.1f} beats ({song.total_bars} bars)")

                # Detect chord progression
                chords = detect_chord_progression_for_song(song)
                if chords.chords:
                    chord_names = [c.chord.name for c in chords.chords[:8]]
                    progression = " → ".join(chord_names)
                    if len(chords.chords) > 8:
                        progression += " ..."
                    click.echo(f"  Chords: {progression}")

                # Show each track with role and stats
                click.echo(f"  Tracks:")
                for i, track in enumerate(song.tracks):
                    if not track.notes:
                        continue

                    # Extract features for role classification
                    track.features = feature_extractor.extract_features(track, song.total_bars or 1)
                    role_probs = classify_track_role(track)
                    role = role_probs.primary_role()

                    # Calculate pitch range
                    pitches = [n.pitch for n in track.notes]
                    pitch_range = f"{min(pitches)}-{max(pitches)}"

                    # Note density
                    if song.total_beats > 0:
                        notes_per_beat = len(track.notes) / song.total_beats
                    else:
                        notes_per_beat = 0

                    track_name = track.name or f"Track {i}"
                    click.echo(
                        f"    [{role.value:6}] {track_name}: "
                        f"{len(track.notes)} notes, "
                        f"pitch {pitch_range}, "
                        f"{notes_per_beat:.1f} notes/beat"
                    )

                    # Show note distribution for drums
                    if role == TrackRole.DRUMS and verbose:
                        # Count notes by pitch (drum sounds)
                        from collections import Counter
                        drum_counts = Counter(n.pitch for n in track.notes)
                        top_drums = drum_counts.most_common(3)
                        drum_names = {
                            36: "kick", 38: "snare", 42: "hihat-c",
                            46: "hihat-o", 41: "tom-lo", 45: "tom-mid",
                            48: "tom-hi", 49: "crash", 51: "ride",
                        }
                        top_str = ", ".join(
                            f"{drum_names.get(p, f'n{p}')}:{c}"
                            for p, c in top_drums
                        )
                        click.echo(f"             Top hits: {top_str}")

                    # Show arpeggio analysis for arp tracks
                    if arpeggios and role == TrackRole.ARP:
                        track.role_probs = role_probs
                        arp_analysis = analyze_arp_track(track, song)
                        if arp_analysis.patterns:
                            click.echo(f"             {color('Arpeggio patterns:', Colors.GREEN)}")
                            for j, pattern in enumerate(arp_analysis.patterns[:3]):
                                intervals = pattern.interval_sequence[:4]
                                interval_str = " ".join(str(i) for i in intervals)
                                click.echo(
                                    f"               [{j+1}] Rate: {pattern.rate}, "
                                    f"Intervals: [{interval_str}], "
                                    f"Gate: {pattern.gate:.2f}"
                                )

            # Section analysis
            if sections:
                section_analysis = analyze_sections(song)
                if section_analysis.sections:
                    click.echo(f"\n  {color('Song Structure:', Colors.BOLD)}")

                    # Show form sequence
                    form_seq = " → ".join(section_analysis.form_sequence)
                    click.echo(f"    Form: {form_seq}")

                    # Show each section
                    for section in section_analysis.sections:
                        type_str = ""
                        if section.type_hint != SectionType.UNKNOWN:
                            confidence_pct = int(section.type_confidence * 100)
                            type_str = f" ({section.type_hint.value} ~{confidence_pct}%)"

                        bars_str = f"bars {section.start_bar + 1}-{section.end_bar}"
                        click.echo(
                            f"    {color(section.form_label, Colors.CYAN)}: {bars_str}{type_str}"
                        )

            success_count += 1

        except Exception as e:
            failed_files.append((file_path, str(e)))
            if verbose:
                click.echo(f"\nError processing {file_path}: {e}", err=True)
                import traceback
                click.echo(traceback.format_exc(), err=True)

    # Summary
    click.echo(f"\n{'=' * 60}")
    click.echo(f"Processed {success_count}/{len(files)} files successfully")

    if failed_files:
        click.echo(f"\nFailed to process {len(failed_files)} file(s):")
        for path, error in failed_files:
            click.echo(f"  - {path.name}: {error[:60]}{'...' if len(error) > 60 else ''}")


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("-v", "--verbose", is_flag=True, help="Show per-bar feature details.")
@click.option("-f", "--format", "output_format", type=click.Choice(["text", "json"]), default="text")
@click.pass_context
def structure(ctx: click.Context, path: Path, verbose: bool, output_format: str) -> None:
    """Analyze song structure and detect sections.

    Detects section boundaries using novelty analysis, clusters similar
    sections into form labels (A/B/C), and provides heuristic type hints
    (intro, verse, chorus, breakdown, etc.).

    Example:
        midi-analyzer structure song.mid
        midi-analyzer structure song.mid --format json
    """
    from midi_analyzer.ingest import parse_midi_file
    from midi_analyzer.harmony import detect_key_for_song
    from midi_analyzer.analysis.sections import analyze_sections, SectionType

    verbose = verbose or ctx.obj.get("verbose", False)

    if not path.is_file():
        click.echo(f"Error: {path} is not a file", err=True)
        raise SystemExit(1)

    try:
        song = parse_midi_file(path)
        key = detect_key_for_song(song)
        analysis = analyze_sections(song)
    except Exception as e:
        click.echo(f"Error analyzing {path}: {e}", err=True)
        raise SystemExit(1)

    if output_format == "json":
        # JSON output for programmatic use
        data = {
            "file": str(path),
            "key": f"{key.root_name} {key.mode.value}",
            "tempo": song.primary_tempo,
            "time_signature": song.primary_time_sig,
            "total_bars": song.total_bars,
            "form_sequence": analysis.form_sequence,
            "sections": [
                {
                    "form_label": s.form_label,
                    "start_bar": s.start_bar,
                    "end_bar": s.end_bar,
                    "start_beat": s.start_beat,
                    "end_beat": s.end_beat,
                    "type_hint": s.type_hint.value,
                    "type_confidence": s.type_confidence,
                }
                for s in analysis.sections
            ],
        }
        if verbose:
            data["bar_features"] = [
                {
                    "bar": bf.bar_number,
                    "active_tracks": bf.active_track_count,
                    "note_count": bf.total_note_count,
                    "velocity": bf.avg_velocity,
                    "density_by_role": bf.density_by_role,
                }
                for bf in analysis.bar_features
            ]
        click.echo(json.dumps(data, indent=2))
        return

    # Text output
    click.echo(f"\n{color('Song Structure Analysis', Colors.BOLD, Colors.HEADER)}")
    click.echo(f"{'=' * 50}")
    click.echo(f"File: {path.name}")
    click.echo(f"Key: {key.root_name} {key.mode.value}")
    click.echo(f"Tempo: {song.primary_tempo:.1f} BPM")
    click.echo(f"Time Sig: {song.primary_time_sig}")
    click.echo(f"Duration: {song.total_bars} bars ({song.total_beats:.1f} beats)")

    if not analysis.sections:
        click.echo("\nNo clear section structure detected.")
        return

    # Form overview
    click.echo(f"\n{color('Form:', Colors.BOLD)} {' → '.join(analysis.form_sequence)}")

    # Section details
    click.echo(f"\n{color('Sections:', Colors.BOLD)}")
    for i, section in enumerate(analysis.sections, 1):
        duration = section.end_bar - section.start_bar
        type_info = ""
        if section.type_hint != SectionType.UNKNOWN:
            type_info = f" • {color(section.type_hint.value, Colors.YELLOW)} ({int(section.type_confidence * 100)}%)"

        click.echo(
            f"  {color(section.form_label, Colors.CYAN, Colors.BOLD)}: "
            f"Bars {section.start_bar + 1}–{section.end_bar} "
            f"({duration} bars){type_info}"
        )

    # Per-bar details if verbose
    if verbose and analysis.bar_features:
        click.echo(f"\n{color('Per-Bar Features:', Colors.BOLD)}")
        click.echo("  Bar | Tracks | Notes | Velocity | Top Role")
        click.echo("  " + "-" * 48)

        for bf in analysis.bar_features:
            # Find dominant role
            if bf.density_by_role:
                top_role = max(bf.density_by_role.items(), key=lambda x: x[1])
                role_str = f"{top_role[0]} ({top_role[1]:.1f})"
            else:
                role_str = "-"

            click.echo(
                f"  {bf.bar_number + 1:3d} | {bf.active_track_count:6d} | "
                f"{bf.total_note_count:5d} | {bf.avg_velocity:8.1f} | {role_str}"
            )


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--track", "-t", type=int, help="Specific track index to analyze (0-based).")
@click.option("-f", "--format", "output_format", type=click.Choice(["text", "json"]), default="text")
@click.option("-v", "--verbose", is_flag=True, help="Show all detected patterns.")
@click.pass_context
def arpeggios(ctx: click.Context, path: Path, track: int | None, output_format: str, verbose: bool) -> None:
    """Extract arpeggio patterns from a MIDI file.

    Analyzes tracks with arp-like characteristics (high note density,
    repetitive patterns, monophonic) and extracts:
    - Note rate (1/16, 1/8, etc.)
    - Interval sequence relative to chord root
    - Octave jumps
    - Gate/sustain ratio

    Examples:
        midi-analyzer arpeggios song.mid
        midi-analyzer arpeggios song.mid --track 2
        midi-analyzer arpeggios song.mid --format json
    """
    from midi_analyzer.ingest import parse_midi_file
    from midi_analyzer.analysis import classify_track_role, FeatureExtractor
    from midi_analyzer.analysis.arpeggios import analyze_arp_track

    verbose = verbose or ctx.obj.get("verbose", False)

    if not path.is_file():
        click.echo(f"Error: {path} is not a file", err=True)
        raise SystemExit(1)

    try:
        song = parse_midi_file(path)
    except Exception as e:
        click.echo(f"Error loading {path}: {e}", err=True)
        raise SystemExit(1)

    feature_extractor = FeatureExtractor()

    # Analyze tracks and find arp candidates
    arp_tracks = []
    for i, t in enumerate(song.tracks):
        if not t.notes:
            continue

        t.features = feature_extractor.extract_features(t, song.total_bars or 1)
        role_probs = classify_track_role(t)
        t.role_probs = role_probs

        # If specific track requested, use it; otherwise filter by arp probability
        if track is not None:
            if i == track:
                arp_tracks.append((i, t, role_probs))
        elif role_probs.arp > 0.3:  # Threshold for arp-like tracks
            arp_tracks.append((i, t, role_probs))

    if not arp_tracks:
        if track is not None:
            click.echo(f"Track {track} not found or has no notes.", err=True)
        else:
            click.echo("No arpeggio-like tracks detected.")
            click.echo("Use --track N to analyze a specific track.")
        raise SystemExit(1)

    results = []
    for track_idx, t, role_probs in arp_tracks:
        analysis = analyze_arp_track(t, song)
        results.append({
            "track_index": track_idx,
            "track_name": t.name or f"Track {track_idx}",
            "arp_probability": role_probs.arp,
            "analysis": analysis,
        })

    if output_format == "json":
        data = {
            "file": str(path),
            "tracks": [
                {
                    "track_index": r["track_index"],
                    "track_name": r["track_name"],
                    "arp_probability": r["arp_probability"],
                    "dominant_rate": r["analysis"].dominant_rate,
                    "avg_gate": r["analysis"].avg_gate,
                    "patterns": [
                        {
                            "rate": p.rate,
                            "interval_sequence": p.interval_sequence,
                            "octave_jumps": p.octave_jumps,
                            "gate": p.gate,
                        }
                        for p in r["analysis"].patterns
                    ],
                    "windows": [
                        {
                            "start_beat": w.start_beat,
                            "end_beat": w.end_beat,
                            "chord": w.inferred_chord.name if w.inferred_chord else None,
                            "rate": w.rate,
                            "interval_sequence": w.interval_sequence[:8],
                        }
                        for w in r["analysis"].windows
                    ] if verbose else [],
                }
                for r in results
            ],
        }
        click.echo(json.dumps(data, indent=2))
        return

    # Text output
    click.echo(f"\n{color('Arpeggio Analysis', Colors.BOLD, Colors.HEADER)}")
    click.echo(f"{'=' * 50}")
    click.echo(f"File: {path.name}")

    for r in results:
        analysis = r["analysis"]
        click.echo(f"\n{color(r['track_name'], Colors.CYAN, Colors.BOLD)}")
        click.echo(f"  Arp probability: {r['arp_probability']:.0%}")
        click.echo(f"  Dominant rate: {color(analysis.dominant_rate, Colors.GREEN)}")
        click.echo(f"  Average gate: {analysis.avg_gate:.2f}")

        if analysis.patterns:
            click.echo(f"\n  {color('Detected Patterns:', Colors.BOLD)}")
            for i, pattern in enumerate(analysis.patterns[:5] if not verbose else analysis.patterns):
                intervals = " ".join(f"{iv:2d}" for iv in pattern.interval_sequence[:8])
                octaves = " ".join(str(o) for o in pattern.octave_jumps[:8]) if pattern.octave_jumps else "-"
                click.echo(
                    f"    [{i+1}] Rate: {pattern.rate:5s} | "
                    f"Intervals: [{intervals}] | "
                    f"Octaves: [{octaves}] | "
                    f"Gate: {pattern.gate:.2f}"
                )

            if not verbose and len(analysis.patterns) > 5:
                click.echo(f"    ... and {len(analysis.patterns) - 5} more (use -v to see all)")

        if verbose and analysis.windows:
            click.echo(f"\n  {color('Analysis Windows:', Colors.BOLD)}")
            for w in analysis.windows:
                chord_name = w.inferred_chord.name if w.inferred_chord else "?"
                click.echo(
                    f"    Bars {w.start_beat/4:.0f}–{w.end_beat/4:.0f}: "
                    f"Chord={chord_name}, Rate={w.rate}"
                )


# =============================================================================
# Library Commands (clip indexing and querying)
# =============================================================================


@cli.group()
def library() -> None:
    """Manage the clip library - index, query, and export MIDI clips."""
    pass


@library.command("index")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("-r", "--recursive", is_flag=True, help="Recursively process directories.")
@click.option("-g", "--genre", multiple=True, help="Genre tags for indexed files.")
@click.option("-a", "--artist", default="", help="Artist name for indexed files.")
@click.option("-t", "--tag", multiple=True, help="Additional tags.")
@click.option(
    "-d", "--database",
    type=click.Path(path_type=Path),
    default=DEFAULT_LIBRARY,
    help="Library database path.",
)
@click.option("-v", "--verbose", is_flag=True, help="Show progress during indexing.")
@click.pass_context
def library_index(
    ctx: click.Context,
    path: Path,
    recursive: bool,
    genre: tuple[str, ...],
    artist: str,
    tag: tuple[str, ...],
    database: Path,
    verbose: bool,
) -> None:
    """Index MIDI files into the clip library.

    PATH can be a single MIDI file or a directory.
    """
    from midi_analyzer.library import ClipLibrary

    verbose = verbose or ctx.obj.get("verbose", False)

    with ClipLibrary(database) as library:
        if path.is_file():
            try:
                clips = library.index_file(
                    path,
                    genres=list(genre) if genre else None,
                    artist=artist,
                    tags=list(tag) if tag else None,
                )
                click.echo(f"Indexed {len(clips)} clip(s) from {path.name}")
            except Exception as e:
                click.echo(f"Error indexing {path.name}: {e}", err=True)
                raise SystemExit(1)
        else:
            failed_files: list[tuple[Path, str]] = []

            def progress(current: int, total: int, filename: str) -> None:
                click.echo(f"  [{current}/{total}] {filename}")

            def on_error(file_path: Path, error: Exception) -> None:
                failed_files.append((file_path, str(error)))
                if verbose:
                    click.echo(f"  Error: {file_path.name}: {error}", err=True)

            count = library.index_directory(
                path,
                recursive=recursive,
                genres=list(genre) if genre else None,
                artist=artist,
                tags=list(tag) if tag else None,
                progress_callback=progress if verbose else None,
                error_callback=on_error,
            )
            click.echo(f"\nIndexed {count} clip(s) from {path}")

            if failed_files:
                click.echo(f"\nFailed to index {len(failed_files)} file(s):")
                for fpath, error in failed_files:
                    click.echo(f"  - {fpath.name}: {error[:50]}{'...' if len(error) > 50 else ''}")


@library.command("query")
@click.option("--role", type=click.Choice(["drums", "bass", "chords", "lead", "arp", "pad", "other"]))
@click.option("-g", "--genre", help="Filter by genre.")
@click.option("-a", "--artist", help="Filter by artist (partial match).")
@click.option("-t", "--tag", multiple=True, help="Filter by tag.")
@click.option("--min-notes", type=int, help="Minimum note count.")
@click.option("--max-notes", type=int, help="Maximum note count.")
@click.option("--min-bars", type=int, help="Minimum duration in bars.")
@click.option("--max-bars", type=int, help="Maximum duration in bars.")
@click.option("-l", "--limit", type=int, default=20, help="Maximum results.")
@click.option(
    "-d", "--database",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_LIBRARY,
    help="Library database path.",
)
@click.pass_context
def library_query(
    ctx: click.Context,
    role: str | None,
    genre: str | None,
    artist: str | None,
    tag: tuple[str, ...],
    min_notes: int | None,
    max_notes: int | None,
    min_bars: int | None,
    max_bars: int | None,
    limit: int,
    database: Path,
) -> None:
    """Query clips from the library.

    Example: midi-analyzer library query --role bass --genre jazz
    """
    from midi_analyzer.library import ClipLibrary, ClipQuery

    with ClipLibrary(database) as library:
        query = ClipQuery(
            role=TrackRole(role) if role else None,
            genre=genre,
            artist=artist,
            min_notes=min_notes,
            max_notes=max_notes,
            min_bars=min_bars,
            max_bars=max_bars,
            tags=list(tag) if tag else None,
            limit=limit,
        )

        clips = library.query(query)

        if not clips:
            click.echo("No clips found matching criteria.")
            return

        click.echo(f"Found {len(clips)} clip(s):\n")

        for clip in clips:
            genres_str = ", ".join(clip.genres) if clip.genres else "none"
            click.echo(
                f"  {clip.clip_id}: {clip.track_name or 'Untitled'}\n"
                f"    Role: {clip.role.value}, Notes: {clip.note_count}, Bars: {clip.duration_bars}\n"
                f"    Artist: {clip.artist or 'Unknown'}, Genres: {genres_str}\n"
                f"    Source: {Path(clip.source_path).name}\n"
            )


@library.command("export")
@click.argument("clip_id")
@click.option(
    "-o", "--output",
    type=click.Path(path_type=Path),
    help="Output MIDI file path.",
)
@click.option("--tempo", type=float, default=120.0, help="Tempo in BPM.")
@click.option("--transpose", type=int, default=0, help="Semitones to transpose.")
@click.option(
    "-d", "--database",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_LIBRARY,
    help="Library database path.",
)
@click.pass_context
def library_export(
    ctx: click.Context,
    clip_id: str,
    output: Path | None,
    tempo: float,
    transpose: int,
    database: Path,
) -> None:
    """Export a clip to a MIDI file.

    Example: midi-analyzer library export abc123_0 -o bass_clip.mid
    """
    from midi_analyzer.export import ExportOptions, export_track
    from midi_analyzer.library import ClipLibrary, ClipQuery

    with ClipLibrary(database) as library:
        # Find the clip
        cursor = library.connection.cursor()
        cursor.execute("SELECT * FROM clips WHERE clip_id = ?", (clip_id,))
        row = cursor.fetchone()

        if not row:
            click.echo(f"Clip '{clip_id}' not found.", err=True)
            raise SystemExit(1)

        clip = library._row_to_clip(row)
        track = library.load_track(clip)

        # Determine output path
        if output is None:
            safe_name = clip.track_name.replace(" ", "_") if clip.track_name else clip_id
            output = Path(f"{safe_name}.mid")

        options = ExportOptions(
            transpose=transpose,
            normalize_start=True,
        )

        export_track(track, output, tempo_bpm=tempo, options=options)
        click.echo(f"Exported clip to {output}")


@library.command("stats")
@click.option(
    "-d", "--database",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_LIBRARY,
    help="Library database path.",
)
@click.pass_context
def library_stats(ctx: click.Context, database: Path) -> None:
    """Show library statistics."""
    from midi_analyzer.library import ClipLibrary

    with ClipLibrary(database) as library:
        stats = library.get_stats()

        click.echo(f"Library Statistics ({database}):\n")
        click.echo(f"  Total clips: {stats.total_clips}")
        click.echo(f"  Total songs: {stats.total_songs}")

        if stats.clips_by_role:
            click.echo("\n  Clips by role:")
            for role, count in sorted(stats.clips_by_role.items()):
                click.echo(f"    {role}: {count}")

        if stats.clips_by_genre:
            click.echo("\n  Top genres:")
            top_genres = sorted(stats.clips_by_genre.items(), key=lambda x: -x[1])[:10]
            for genre, count in top_genres:
                click.echo(f"    {genre}: {count}")

        if stats.artists:
            click.echo(f"\n  Artists: {len(stats.artists)}")
            for artist in stats.artists[:10]:
                click.echo(f"    - {artist}")
            if len(stats.artists) > 10:
                click.echo(f"    ... and {len(stats.artists) - 10} more")


@library.command("list-genres")
@click.option(
    "-d", "--database",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_LIBRARY,
    help="Library database path.",
)
def library_list_genres(database: Path) -> None:
    """List all genres in the library."""
    from midi_analyzer.library import ClipLibrary

    with ClipLibrary(database) as library:
        genres = library.list_genres()

        if not genres:
            click.echo("No genres found in library.")
            return

        click.echo(f"Genres ({len(genres)}):")
        for genre in genres:
            click.echo(f"  - {genre}")


@library.command("list-artists")
@click.option(
    "-d", "--database",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_LIBRARY,
    help="Library database path.",
)
def library_list_artists(database: Path) -> None:
    """List all artists in the library."""
    from midi_analyzer.library import ClipLibrary

    with ClipLibrary(database) as library:
        artists = library.list_artists()

        if not artists:
            click.echo("No artists found in library.")
            return

        click.echo(f"Artists ({len(artists)}):")
        for artist in artists:
            click.echo(f"  - {artist}")


@library.command("enrich")
@click.option(
    "-d", "--database",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_LIBRARY,
    help="Library database path.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be updated without making changes.",
)
@click.pass_context
def library_enrich(ctx: click.Context, database: Path, dry_run: bool) -> None:
    """Enrich library clips with genre tags from MusicBrainz.

    Queries MusicBrainz for each unique artist to fetch genre/style tags,
    then updates all clips by that artist. Rate limited to 1 request/second.
    """
    from midi_analyzer.library import ClipLibrary
    from midi_analyzer.metadata.musicbrainz import get_genre_tags, search_artist

    verbose = ctx.obj.get("verbose", False) if ctx.obj else False

    with ClipLibrary(database) as lib:
        # Get unique artists
        artists = lib.list_artists()

        if not artists:
            click.echo("No artists found in library.")
            return

        click.echo(f"Found {len(artists)} unique artist(s). Querying MusicBrainz...")
        click.echo("(Rate limited to 1 request/second)\n")

        updated_count = 0
        skipped_count = 0
        error_count = 0

        for i, artist in enumerate(artists, 1):
            if not artist:
                skipped_count += 1
                continue

            # For collaborations like "Artist1, Artist2", search for first artist
            search_artist_name = artist.split(",")[0].strip()

            try:
                # Search for artist to get their tags
                artist_results = search_artist(search_artist_name, limit=1)

                tags: list[str] = []
                if artist_results:
                    tags = artist_results[0].tags

                if verbose or tags:
                    status = f"[{i}/{len(artists)}] {artist}"
                    if tags:
                        click.echo(f"{status}: {', '.join(tags[:5])}")
                    elif verbose:
                        click.echo(f"{status}: (no tags found)")

                if tags and not dry_run:
                    # Update all clips by this artist
                    cursor = lib.connection.cursor()
                    cursor.execute(
                        "SELECT clip_id, genres FROM clips WHERE artist = ?",
                        (artist,),
                    )
                    rows = cursor.fetchall()

                    for row in rows:
                        clip_id = row[0]
                        existing = json.loads(row[1]) if row[1] else []
                        # Merge tags, avoiding duplicates
                        merged = list(dict.fromkeys(existing + tags))
                        lib.update_metadata(clip_id, genres=merged)
                        updated_count += 1

                elif tags:
                    # Dry run - count what would be updated
                    cursor = lib.connection.cursor()
                    cursor.execute(
                        "SELECT COUNT(*) FROM clips WHERE artist = ?",
                        (artist,),
                    )
                    count = cursor.fetchone()[0]
                    updated_count += count

            except Exception as e:
                error_count += 1
                if verbose:
                    click.echo(f"[{i}/{len(artists)}] {artist}: ERROR - {e}", err=True)

        click.echo()
        if dry_run:
            click.echo(f"Dry run complete. Would update {updated_count} clip(s).")
        else:
            click.echo(f"Enriched {updated_count} clip(s) with genre tags.")

        if skipped_count:
            click.echo(f"Skipped {skipped_count} clip(s) with no artist.")
        if error_count:
            click.echo(f"Errors: {error_count}")


@cli.command()
@click.option("--role", type=click.Choice(["drums", "bass", "chords", "lead", "arp", "pad"]))
@click.option("--meter", help="Time signature (e.g., '4/4', '3/4').")
@click.option("--genre", help="Filter by genre.")
@click.option("--tag", multiple=True, help="Filter by tag (can specify multiple).")
@click.option("--limit", type=int, default=20, help="Maximum results to return.")
@click.option(
    "-d",
    "--database",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_LIBRARY,
    help="Pattern database path.",
)
@click.pass_context
def search(
    ctx: click.Context,
    role: str | None,
    meter: str | None,
    genre: str | None,
    tag: tuple[str, ...],
    limit: int,
    database: Path,
) -> None:
    """Search for patterns in the library.

    Shortcut for 'library query'. For more options, use 'library query'.
    """
    from midi_analyzer.library import ClipLibrary, ClipQuery

    verbose = ctx.obj.get("verbose", False)

    with ClipLibrary(database) as library:
        query = ClipQuery(
            role=TrackRole(role) if role else None,
            genre=genre,
            tags=list(tag) if tag else None,
            limit=limit,
        )

        clips = library.query(query)

        if not clips:
            click.echo("No patterns found matching criteria.")
            return

        click.echo(f"Found {len(clips)} pattern(s):\n")

        for clip in clips:
            genres_str = ", ".join(clip.genres) if clip.genres else ""
            artist_str = f" by {clip.artist}" if clip.artist else ""
            click.echo(
                f"  {clip.clip_id}: {clip.track_name or 'Untitled'} [{clip.role.value}]{artist_str}"
            )
            if verbose and genres_str:
                click.echo(f"    Genres: {genres_str}")


@cli.command()
@click.option(
    "-d",
    "--database",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_LIBRARY,
    help="Pattern database path.",
)
@click.pass_context
def stats(ctx: click.Context, database: Path) -> None:
    """Show statistics about the pattern library.

    Shortcut for 'library stats'.
    """
    # Delegate to library stats
    from midi_analyzer.library import ClipLibrary

    with ClipLibrary(database) as library:
        stats_info = library.get_stats()

        click.echo(f"Library: {database}\n")
        click.echo(f"  Clips: {stats_info.total_clips}")
        click.echo(f"  Songs: {stats_info.total_songs}")

        if stats_info.clips_by_role:
            click.echo("\n  By role:")
            for role, count in sorted(stats_info.clips_by_role.items()):
                click.echo(f"    {role}: {count}")


@cli.command()
@click.argument("clip_id")
@click.option(
    "-f",
    "--format",
    "output_format",
    type=click.Choice(["json", "midi"]),
    default="midi",
    help="Export format.",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file path.",
)
@click.option("--tempo", type=float, default=120.0, help="Tempo in BPM (for MIDI export).")
@click.option("--transpose", type=int, default=0, help="Semitones to transpose.")
@click.option(
    "-d",
    "--database",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_LIBRARY,
    help="Pattern database path.",
)
@click.pass_context
def export(
    ctx: click.Context,
    clip_id: str,
    output_format: str,
    output: Path | None,
    tempo: float,
    transpose: int,
    database: Path,
) -> None:
    """Export a pattern/clip to JSON or MIDI format.

    CLIP_ID is the clip identifier (use 'search' or 'library query' to find IDs).
    """
    import json

    from midi_analyzer.export import ExportOptions, export_track
    from midi_analyzer.library import ClipLibrary

    with ClipLibrary(database) as library:
        # Find the clip
        cursor = library.connection.cursor()
        cursor.execute("SELECT * FROM clips WHERE clip_id = ?", (clip_id,))
        row = cursor.fetchone()

        if not row:
            click.echo(f"Clip '{clip_id}' not found.", err=True)
            raise SystemExit(1)

        clip = library._row_to_clip(row)
        track = library.load_track(clip)

        if output_format == "json":
            # Export as JSON
            data = {
                "clip_id": clip.clip_id,
                "track_name": clip.track_name,
                "role": clip.role.value,
                "artist": clip.artist,
                "genres": clip.genres,
                "note_count": clip.note_count,
                "notes": [
                    {
                        "pitch": n.pitch,
                        "velocity": n.velocity,
                        "start_beat": n.start_beat,
                        "duration_beats": n.duration_beats,
                    }
                    for n in track.notes
                ],
            }
            if output:
                output.write_text(json.dumps(data, indent=2))
                click.echo(f"Exported to {output}")
            else:
                click.echo(json.dumps(data, indent=2))
        else:
            # Export as MIDI
            if output is None:
                safe_name = clip.track_name.replace(" ", "_") if clip.track_name else clip_id
                output = Path(f"{safe_name}.mid")

            options = ExportOptions(
                transpose=transpose,
                normalize_start=True,
            )

            export_track(track, output, tempo_bpm=tempo, options=options)
            click.echo(f"Exported to {output}")


@cli.command()
@click.argument("source")
@click.option("--tempo", type=float, default=120.0, help="Playback tempo in BPM.")
@click.option("--transpose", type=int, default=0, help="Semitones to transpose.")
@click.option("--loop", is_flag=True, help="Loop playback.")
@click.option("--instrument", type=int, help="Override instrument (GM program 0-127).")
@click.option(
    "-d",
    "--database",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_LIBRARY,
    help="Library database path (for clip playback).",
)
@click.option("-v", "--verbose", is_flag=True, help="Show detailed playback info.")
@click.pass_context
def play(
    ctx: click.Context,
    source: str,
    tempo: float,
    transpose: int,
    loop: bool,
    instrument: int | None,
    database: Path,
    verbose: bool,
) -> None:
    """Play a MIDI file or clip from the library.

    SOURCE can be a MIDI file path or a clip ID from the library.

    Examples:

      midi-analyzer play song.mid

      midi-analyzer play abc123_0 --tempo 140

      midi-analyzer play clip_id --loop
    """
    from midi_analyzer.player import (
        MidiPlayer,
        PlaybackOptions,
        get_instrument_for_role,
        get_instrument_name,
    )

    verbose = verbose or ctx.obj.get("verbose", False)

    # Determine if source is a file or clip ID
    source_path = Path(source)
    is_file = source_path.exists() and source_path.suffix.lower() in (".mid", ".midi")

    if is_file:
        # Play MIDI file directly
        from midi_analyzer.ingest import parse_midi_file

        click.echo(f"Loading {source_path.name}...")
        song = parse_midi_file(source_path)

        # Use song's tempo if not overridden
        if tempo == 120.0 and song.primary_tempo != 120.0:
            tempo = song.primary_tempo

        click.echo(f"Playing: {len(song.tracks)} track(s), {song.total_bars} bars @ {tempo:.0f} BPM")
        click.echo("Press Ctrl+C to stop.\n")

        options = PlaybackOptions(
            tempo_bpm=tempo,
            transpose=transpose,
            loop=loop,
            instrument=instrument,
        )

        try:
            with MidiPlayer() as player:
                for i, track in enumerate(song.tracks):
                    if not track.notes:
                        continue

                    from midi_analyzer.analysis.roles import classify_track_role
                    role = classify_track_role(track)
                    prog = instrument if instrument is not None else get_instrument_for_role(role)
                    inst_name = get_instrument_name(prog) if role.value != "drums" else "Drums"

                    click.echo(f"  Track {i + 1}: {track.name or 'Untitled'} [{role.value}] -> {inst_name}")
                    player.play_track(track, options)

        except KeyboardInterrupt:
            click.echo("\nStopped.")
    else:
        # Try to play from library
        from midi_analyzer.library import ClipLibrary

        with ClipLibrary(database) as library:
            cursor = library.connection.cursor()
            cursor.execute("SELECT * FROM clips WHERE clip_id = ?", (source,))
            row = cursor.fetchone()

            if not row:
                click.echo(f"'{source}' is not a valid file or clip ID.", err=True)
                raise SystemExit(1)

            clip = library._row_to_clip(row)
            track = library.load_track(clip)

            # Get instrument for role
            prog = instrument if instrument is not None else get_instrument_for_role(clip.role)
            inst_name = get_instrument_name(prog) if clip.role.value != "drums" else "Drums"

            click.echo(f"Playing: {clip.track_name or clip.clip_id}")
            click.echo(f"  Role: {clip.role.value} -> {inst_name}")
            click.echo(f"  Notes: {clip.note_count}, Bars: {clip.duration_bars}")
            click.echo(f"  Tempo: {tempo:.0f} BPM")
            if verbose and clip.genres:
                click.echo(f"  Genres: {', '.join(clip.genres)}")
            click.echo("\nPress Ctrl+C to stop.\n")

            options = PlaybackOptions(
                tempo_bpm=tempo,
                transpose=transpose,
                loop=loop,
                instrument=instrument,
            )

            try:
                with MidiPlayer() as player:
                    player.play_track(track, options)
            except KeyboardInterrupt:
                click.echo("\nStopped.")


@cli.command()
@click.option(
    "-d",
    "--db",
    "db_path",
    type=click.Path(path_type=Path),
    default=DEFAULT_LIBRARY,
    help="Path to library database.",
)
def gui(db_path: Path) -> None:
    """Launch the graphical user interface.
    
    Requires PyQt6 to be installed: pip install midi-analyzer[gui]
    """
    try:
        from midi_analyzer.gui import run_gui
    except ImportError as e:
        click.echo(
            f"GUI dependencies not installed: {e}\n\n"
            "Install with: pip install midi-analyzer[gui]",
            err=True,
        )
        raise SystemExit(1)
    
    click.echo(f"Launching GUI with database: {db_path}")
    run_gui(db_path)


@cli.command("list-devices")
def list_devices() -> None:
    """List available MIDI output devices."""
    from midi_analyzer.player import list_midi_devices

    devices = list_midi_devices()

    if not devices:
        click.echo("No MIDI devices found.")
        click.echo("Make sure pygame is installed: pip install pygame")
        return

    click.echo("MIDI Devices:\n")
    for device_id, name, is_output in devices:
        direction = "OUT" if is_output else "IN"
        click.echo(f"  [{device_id}] {name} ({direction})")


if __name__ == "__main__":
    cli()
