"""Tests for CLI commands."""

from click.testing import CliRunner

from midi_analyzer.cli.main import cli


class TestCLI:
    """Tests for the CLI interface."""

    def test_version(self) -> None:
        """Test --version flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "midi-analyzer" in result.output
        assert "0.1.0" in result.output

    def test_help(self) -> None:
        """Test --help flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "MIDI Pattern Extractor" in result.output
        assert "analyze" in result.output
        assert "search" in result.output
        assert "stats" in result.output

    def test_analyze_help(self) -> None:
        """Test analyze --help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "Analyze MIDI files" in result.output
        assert "--recursive" in result.output

    def test_search_help(self) -> None:
        """Test search --help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "--help"])
        assert result.exit_code == 0
        assert "--role" in result.output
        assert "--meter" in result.output
        assert "--genre" in result.output

    def test_analyze_nonexistent_path(self) -> None:
        """Test analyze with nonexistent path."""
        runner = CliRunner()
        result = runner.invoke(cli, ["analyze", "/nonexistent/path"])
        assert result.exit_code != 0
