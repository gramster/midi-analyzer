"""Main CLI entry point for MIDI Analyzer."""

from __future__ import annotations

from pathlib import Path

import click

from midi_analyzer import __version__


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
@click.pass_context
def analyze(
    ctx: click.Context,
    path: Path,
    recursive: bool,
    output: Path,
    skip_genre: bool,
) -> None:
    """Analyze MIDI files and extract patterns.

    PATH can be a single MIDI file or a directory containing MIDI files.
    """
    verbose = ctx.obj.get("verbose", False)

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

    # TODO: Implement actual analysis pipeline
    click.echo("Analysis pipeline not yet implemented")
    click.echo(f"Would write to: {output}")


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
    default="patterns.db",
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
    """Search for patterns in the library."""
    verbose = ctx.obj.get("verbose", False)

    filters = []
    if role:
        filters.append(f"role={role}")
    if meter:
        filters.append(f"meter={meter}")
    if genre:
        filters.append(f"genre={genre}")
    for t in tag:
        filters.append(f"tag={t}")

    if verbose:
        click.echo(f"Searching with filters: {', '.join(filters) or 'none'}")
        click.echo(f"Database: {database}")

    # TODO: Implement pattern search
    click.echo("Pattern search not yet implemented")


@cli.command()
@click.option(
    "-d",
    "--database",
    type=click.Path(exists=True, path_type=Path),
    default="patterns.db",
    help="Pattern database path.",
)
@click.pass_context
def stats(ctx: click.Context, database: Path) -> None:
    """Show statistics about the pattern library."""
    verbose = ctx.obj.get("verbose", False)

    if verbose:
        click.echo(f"Database: {database}")

    # TODO: Implement stats display
    click.echo("Statistics display not yet implemented")


@cli.command()
@click.argument("pattern_id")
@click.option(
    "-f",
    "--format",
    "output_format",
    type=click.Choice(["json", "midi"]),
    default="json",
    help="Export format.",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file path.",
)
@click.option(
    "-d",
    "--database",
    type=click.Path(exists=True, path_type=Path),
    default="patterns.db",
    help="Pattern database path.",
)
@click.pass_context
def export(
    ctx: click.Context,
    pattern_id: str,
    output_format: str,
    output: Path | None,
    database: Path,
) -> None:
    """Export a pattern to JSON or MIDI format."""
    verbose = ctx.obj.get("verbose", False)

    if verbose:
        click.echo(f"Exporting pattern {pattern_id} as {output_format}")
        click.echo(f"Database: {database}")

    # TODO: Implement pattern export
    click.echo("Pattern export not yet implemented")


if __name__ == "__main__":
    cli()
