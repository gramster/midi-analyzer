"""Tests for batch processing."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from midi_analyzer.processing import (
    BatchConfig,
    BatchProcessor,
    BatchProgress,
    BatchState,
    ProcessingResult,
    create_simple_processor,
    process_directory_simple,
)


class TestProcessingResult:
    """Tests for ProcessingResult dataclass."""

    def test_creation_success(self):
        """Test creating a successful result."""
        result = ProcessingResult(
            path=Path("/test.mid"),
            success=True,
            song_id="song-123",
            duration_ms=150.0,
        )

        assert result.success
        assert result.song_id == "song-123"
        assert result.error is None

    def test_creation_failure(self):
        """Test creating a failed result."""
        result = ProcessingResult(
            path=Path("/test.mid"),
            success=False,
            error="Parse error",
        )

        assert not result.success
        assert result.error == "Parse error"


class TestBatchProgress:
    """Tests for BatchProgress dataclass."""

    def test_progress_percent(self):
        """Test progress percentage calculation."""
        progress = BatchProgress(total=100, processed=25)
        assert progress.progress_percent == 25.0

    def test_progress_percent_zero_total(self):
        """Test progress with zero total."""
        progress = BatchProgress(total=0)
        assert progress.progress_percent == 0.0

    def test_rate_per_second(self):
        """Test processing rate calculation."""
        progress = BatchProgress(total=100, processed=50, elapsed_ms=10000)
        assert progress.rate_per_second == 5.0

    def test_rate_zero_time(self):
        """Test rate with zero elapsed time."""
        progress = BatchProgress(total=100, processed=50, elapsed_ms=0)
        assert progress.rate_per_second == 0.0


class TestBatchConfig:
    """Tests for BatchConfig dataclass."""

    def test_default_config(self):
        """Test default configuration."""
        config = BatchConfig()

        assert config.workers == 4
        assert config.skip_existing is True
        assert config.resume is True
        assert config.checkpoint_interval == 100

    def test_custom_config(self):
        """Test custom configuration."""
        config = BatchConfig(
            workers=8,
            skip_existing=False,
            checkpoint_interval=50,
        )

        assert config.workers == 8
        assert config.skip_existing is False


class TestBatchState:
    """Tests for BatchState dataclass."""

    def test_default_state(self):
        """Test default state."""
        state = BatchState()
        assert len(state.processed_files) == 0
        assert state.checkpoint_path is None

    def test_with_processed_files(self):
        """Test state with processed files."""
        state = BatchState(processed_files={"hash1", "hash2"})
        assert len(state.processed_files) == 2


class TestBatchProcessor:
    """Tests for BatchProcessor class."""

    @pytest.fixture
    def mock_process_func(self):
        """Create a mock process function."""
        mock = MagicMock()
        mock.return_value = MagicMock(song_id="test-song")
        return mock

    @pytest.fixture
    def processor(self, mock_process_func):
        """Create a test processor."""
        return BatchProcessor(process_func=mock_process_func)

    def test_file_hash(self, processor, tmp_path):
        """Test file hash generation."""
        test_file = tmp_path / "test.mid"
        test_file.write_bytes(b"test content")

        hash1 = processor._get_file_hash(test_file)
        hash2 = processor._get_file_hash(test_file)

        assert hash1 == hash2
        assert len(hash1) == 32  # MD5 hex length

    def test_process_file_success(self, processor, tmp_path):
        """Test successful file processing."""
        test_file = tmp_path / "test.mid"
        test_file.write_bytes(b"test")

        result = processor._process_file(test_file)

        assert result.success
        assert result.song_id == "test-song"
        assert result.duration_ms > 0

    def test_process_file_error(self, tmp_path):
        """Test processing with error."""
        def error_func(path):
            raise ValueError("Test error")

        processor = BatchProcessor(process_func=error_func)
        test_file = tmp_path / "test.mid"
        test_file.write_bytes(b"test")

        result = processor._process_file(test_file)

        assert not result.success
        assert "Test error" in result.error

    def test_process_file_returns_none(self, tmp_path):
        """Test processing that returns None."""
        processor = BatchProcessor(process_func=lambda p: None)
        test_file = tmp_path / "test.mid"
        test_file.write_bytes(b"test")

        result = processor._process_file(test_file)

        assert not result.success
        assert "None" in result.error


class TestBatchProcessorFiles:
    """Tests for batch file processing."""

    @pytest.fixture
    def mock_process_func(self):
        """Create a mock process function."""
        def process(path):
            mock_song = MagicMock()
            mock_song.song_id = f"song-{path.stem}"
            return mock_song

        return process

    @pytest.fixture
    def processor(self, mock_process_func):
        """Create a test processor."""
        return BatchProcessor(process_func=mock_process_func)

    @pytest.fixture
    def test_files(self, tmp_path):
        """Create test MIDI files."""
        files = []
        for i in range(5):
            f = tmp_path / f"test{i}.mid"
            f.write_bytes(f"content {i}".encode())
            files.append(f)
        return files

    def test_process_files_sequential(self, processor, test_files):
        """Test sequential file processing."""
        config = BatchConfig(workers=1)
        results = processor.process_files(test_files, config)

        assert len(results) == 5
        assert all(r.success for r in results)

    def test_process_files_parallel(self, processor, test_files):
        """Test parallel file processing."""
        config = BatchConfig(workers=4)
        results = processor.process_files(test_files, config)

        assert len(results) == 5
        assert all(r.success for r in results)

    def test_skip_existing(self, processor, test_files):
        """Test skipping existing files."""
        # Process once
        config = BatchConfig(workers=1, skip_existing=True)
        processor.process_files(test_files, config)

        # Process again - should skip all
        results = processor.process_files(test_files, config)

        assert len(results) == 0
        assert processor.get_progress().skipped == 5

    def test_progress_callback(self, processor, test_files):
        """Test progress callback."""
        progress_updates = []

        def on_progress(progress):
            progress_updates.append(progress.processed)

        config = BatchConfig(workers=1, on_progress=on_progress)
        processor.process_files(test_files, config)

        # Should have progress updates
        assert len(progress_updates) > 0

    def test_file_complete_callback(self, processor, test_files):
        """Test file complete callback."""
        results_received = []

        def on_complete(result):
            results_received.append(result)

        config = BatchConfig(workers=1, on_file_complete=on_complete)
        processor.process_files(test_files, config)

        assert len(results_received) == 5

    def test_file_filter(self, processor, test_files, tmp_path):
        """Test file filtering."""
        # Add non-matching file
        skip_file = tmp_path / "skip.mid"
        skip_file.write_bytes(b"skip")
        test_files.append(skip_file)

        def filter_func(path):
            return "skip" not in path.name

        config = BatchConfig(workers=1, file_filter=filter_func)
        results = processor.process_files(test_files, config)

        assert len(results) == 5  # Skip file excluded


class TestCheckpoints:
    """Tests for checkpoint functionality."""

    @pytest.fixture
    def mock_process_func(self):
        """Create a mock process function."""
        def process(path):
            mock_song = MagicMock()
            mock_song.song_id = f"song-{path.stem}"
            return mock_song

        return process

    @pytest.fixture
    def processor(self, mock_process_func):
        """Create a test processor."""
        return BatchProcessor(process_func=mock_process_func)

    def test_save_and_load_checkpoint(self, processor, tmp_path):
        """Test saving and loading checkpoints."""
        checkpoint_path = tmp_path / "checkpoint.txt"

        # Add some processed files
        processor._state.processed_files = {"hash1", "hash2", "hash3"}
        processor._state.checkpoint_path = checkpoint_path

        # Save
        processor._save_checkpoint()
        assert checkpoint_path.exists()

        # Load into new processor
        new_processor = BatchProcessor(process_func=lambda p: None)
        new_processor._load_checkpoint(checkpoint_path)

        assert "hash1" in new_processor._state.processed_files
        assert "hash2" in new_processor._state.processed_files
        assert "hash3" in new_processor._state.processed_files

    def test_resume_from_checkpoint(self, mock_process_func, tmp_path):
        """Test resuming from checkpoint."""
        checkpoint_path = tmp_path / "checkpoint.txt"

        # Create files
        files = []
        for i in range(5):
            f = tmp_path / f"test{i}.mid"
            f.write_bytes(f"content {i}".encode())
            files.append(f)

        # First run - process first 3
        processor1 = BatchProcessor(process_func=mock_process_func)
        config = BatchConfig(workers=1, resume=True)

        # Manually mark first 3 as processed
        processor1.process_files(files[:3], config, checkpoint_path)

        # Second run - should skip the processed files
        processor2 = BatchProcessor(process_func=mock_process_func)
        results = processor2.process_files(files, config, checkpoint_path)

        # Only 2 new files should be processed
        assert len(results) == 2


class TestDirectoryProcessing:
    """Tests for directory processing."""

    @pytest.fixture
    def mock_process_func(self):
        """Create a mock process function."""
        def process(path):
            mock_song = MagicMock()
            mock_song.song_id = f"song-{path.stem}"
            return mock_song

        return process

    def test_process_directory(self, mock_process_func, tmp_path):
        """Test processing a directory."""
        # Create test files
        for i in range(3):
            f = tmp_path / f"test{i}.mid"
            f.write_bytes(b"content")

        processor = BatchProcessor(process_func=mock_process_func)
        config = BatchConfig(workers=1, skip_existing=False)

        results = processor.process_directory(tmp_path, config, recursive=False)

        assert len(results) == 3

    def test_process_directory_recursive(self, mock_process_func, tmp_path):
        """Test recursive directory processing."""
        # Create nested structure
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        (tmp_path / "test1.mid").write_bytes(b"content")
        (subdir / "test2.mid").write_bytes(b"content")

        processor = BatchProcessor(process_func=mock_process_func)
        config = BatchConfig(workers=1, skip_existing=False)

        results = processor.process_directory(tmp_path, config, recursive=True)

        assert len(results) == 2

    def test_process_directory_extensions(self, mock_process_func, tmp_path):
        """Test filtering by extensions."""
        (tmp_path / "test1.mid").write_bytes(b"content")
        (tmp_path / "test2.midi").write_bytes(b"content")
        (tmp_path / "test3.txt").write_bytes(b"content")

        processor = BatchProcessor(process_func=mock_process_func)
        config = BatchConfig(workers=1, skip_existing=False)

        results = processor.process_directory(
            tmp_path, config, extensions=(".mid", ".midi")
        )

        assert len(results) == 2


class TestStopProcessing:
    """Tests for stopping processing."""

    def test_stop_request(self):
        """Test stop request."""
        processor = BatchProcessor(process_func=lambda p: MagicMock(song_id="x"))
        processor.stop()

        assert processor._stop_requested


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_create_simple_processor(self):
        """Test creating a simple processor."""
        mock_func = MagicMock()
        processor = create_simple_processor(mock_func)

        assert isinstance(processor, BatchProcessor)
        assert processor.process_func is mock_func

    def test_process_directory_simple(self, tmp_path):
        """Test simple directory processing."""
        # Create test file
        (tmp_path / "test.mid").write_bytes(b"content")

        results = []

        def mock_parse(path):
            mock_song = MagicMock()
            mock_song.song_id = "test"
            return mock_song

        results = process_directory_simple(
            tmp_path,
            parse_func=mock_parse,
            workers=1,
        )

        assert len(results) == 1
