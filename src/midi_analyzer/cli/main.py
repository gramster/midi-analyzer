"""Main CLI entry point for MIDI Analyzer."""

from __future__ import annotations

from pathlib import Path

import click

from midi_analyzer import __version__
from midi_analyzer.models.core import TrackRole


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
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output database path.",
    default="patterns.db",
)
@click.option(
    "--skip-genre",
    is_flag=True,
    help="Skip genre/tag retrieval from web APIs.",
)
@click.option("-v", "--verbose", is_flag=True, help="Show detailed analysis output.")
@click.pass_context
def analyze(
    ctx: click.Context,
    path: Path,
    recursive: bool,
    output: Path,
    skip_genre: bool,
    verbose: bool,
) -> None:
    """Analyze MIDI files and extract patterns.

    PATH can be a single MIDI file or a directory containing MIDI files.
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
    from midi_analyzer.analysis import classify_track_role

    for file_path in files:
        try:
            song = parse_midi_file(file_path)
            key = detect_key_for_song(song)

            # Basic summary line
            click.echo(f"\n{file_path.name}: {key.root_name} {key.mode.value} ({len(song.tracks)} tracks)")

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

        except Exception as e:
            click.echo(f"Error processing {file_path}: {e}", err=True)
            if verbose:
                import traceback
                click.echo(traceback.format_exc(), err=True)


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
@click.pass_context
def library_index(
    ctx: click.Context,
    path: Path,
    recursive: bool,
    genre: tuple[str, ...],
    artist: str,
    tag: tuple[str, ...],
    database: Path,
) -> None:
    """Index MIDI files into the clip library.

    PATH can be a single MIDI file or a directory.
    """
    from midi_analyzer.library import ClipLibrary

    verbose = ctx.obj.get("verbose", False)

    with ClipLibrary(database) as library:
        if path.is_file():
            clips = library.index_file(
                path,
                genres=list(genre) if genre else None,
                artist=artist,
                tags=list(tag) if tag else None,
            )
            click.echo(f"Indexed {len(clips)} clip(s) from {path.name}")
        else:
            def progress(current: int, total: int, filename: str) -> None:
                if verbose:
                    click.echo(f"  [{current}/{total}] {filename}")

            count = library.index_directory(
                path,
                recursive=recursive,
                genres=list(genre) if genre else None,
                artist=artist,
                tags=list(tag) if tag else None,
                progress_callback=progress if verbose else None,
            )
            click.echo(f"Indexed {count} clip(s) from {path}")


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
@click.pass_context
def play(
    ctx: click.Context,
    source: str,
    tempo: float,
    transpose: int,
    loop: bool,
    instrument: int | None,
    database: Path,
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

    verbose = ctx.obj.get("verbose", False)

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
