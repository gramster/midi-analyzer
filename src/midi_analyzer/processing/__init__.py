"""Batch processing for large MIDI file collections."""

from __future__ import annotations

import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from midi_analyzer.models.core import Song

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result of processing a single file.

    Attributes:
        path: Path to the processed file.
        success: Whether processing succeeded.
        song_id: ID of the processed song (if successful).
        duration_ms: Processing time in milliseconds.
        error: Error message if failed.
    """

    path: Path
    success: bool
    song_id: str | None = None
    duration_ms: float = 0.0
    error: str | None = None


@dataclass
class BatchProgress:
    """Progress information for batch processing.

    Attributes:
        total: Total number of files.
        processed: Number of files processed.
        succeeded: Number of successful processings.
        failed: Number of failed processings.
        skipped: Number of skipped files.
        current_file: Currently processing file.
        start_time: Start timestamp.
        elapsed_ms: Elapsed time in milliseconds.
        estimated_remaining_ms: Estimated remaining time.
    """

    total: int
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    current_file: str = ""
    start_time: float = 0.0
    elapsed_ms: float = 0.0
    estimated_remaining_ms: float = 0.0

    @property
    def progress_percent(self) -> float:
        """Get progress as percentage."""
        return (self.processed / self.total * 100) if self.total > 0 else 0.0

    @property
    def rate_per_second(self) -> float:
        """Get processing rate (files per second)."""
        if self.elapsed_ms <= 0:
            return 0.0
        return self.processed / (self.elapsed_ms / 1000)


@dataclass
class BatchConfig:
    """Configuration for batch processing.

    Attributes:
        workers: Number of parallel workers.
        skip_existing: Whether to skip already-processed files.
        resume: Whether to resume from last checkpoint.
        checkpoint_interval: Save checkpoint every N files.
        on_progress: Callback for progress updates.
        on_file_complete: Callback when a file completes.
        file_filter: Optional filter function for files.
    """

    workers: int = 4
    skip_existing: bool = True
    resume: bool = True
    checkpoint_interval: int = 100
    on_progress: Callable[[BatchProgress], None] | None = None
    on_file_complete: Callable[[ProcessingResult], None] | None = None
    file_filter: Callable[[Path], bool] | None = None


@dataclass
class BatchState:
    """State for resumable batch processing.

    Attributes:
        processed_files: Set of already-processed file hashes.
        last_checkpoint: Last checkpoint timestamp.
        checkpoint_path: Path to checkpoint file.
    """

    processed_files: set[str] = field(default_factory=set)
    last_checkpoint: float = 0.0
    checkpoint_path: Path | None = None


class BatchProcessor:
    """Batch processor for large MIDI file collections.

    This class handles processing large numbers of MIDI files with:
    - Parallel processing with configurable worker count
    - Progress reporting
    - Resume from interruption
    - Skip already-processed files

    Example:
        processor = BatchProcessor(process_func=my_process_func)
        results = processor.process_directory(
            Path("/path/to/midi/files"),
            config=BatchConfig(workers=8),
        )
    """

    def __init__(
        self,
        process_func: Callable[[Path], Song | None],
        db_path: Path | None = None,
    ) -> None:
        """Initialize the batch processor.

        Args:
            process_func: Function to process a single MIDI file.
            db_path: Optional path for state database.
        """
        self.process_func = process_func
        self.db_path = db_path
        self._state = BatchState()
        self._progress = BatchProgress(total=0)
        self._stop_requested = False

    def _get_file_hash(self, path: Path) -> str:
        """Get a unique hash for a file.

        Args:
            path: Path to the file.

        Returns:
            Hash string.
        """
        # Use path and modification time for quick hash
        stat = path.stat()
        data = f"{path}:{stat.st_size}:{stat.st_mtime}"
        return hashlib.md5(data.encode()).hexdigest()

    def _save_checkpoint(self) -> None:
        """Save current state to checkpoint file."""
        if not self._state.checkpoint_path:
            return

        checkpoint_data = "\n".join(sorted(self._state.processed_files))
        self._state.checkpoint_path.write_text(checkpoint_data)
        self._state.last_checkpoint = time.time()

    def _load_checkpoint(self, checkpoint_path: Path) -> None:
        """Load state from checkpoint file.

        Args:
            checkpoint_path: Path to checkpoint file.
        """
        self._state.checkpoint_path = checkpoint_path

        if checkpoint_path.exists():
            data = checkpoint_path.read_text()
            self._state.processed_files = set(data.strip().split("\n")) if data.strip() else set()
            logger.info(f"Loaded {len(self._state.processed_files)} processed files from checkpoint")

    def _should_skip(self, path: Path, config: BatchConfig) -> bool:
        """Check if a file should be skipped.

        Args:
            path: Path to check.
            config: Batch configuration.

        Returns:
            True if file should be skipped.
        """
        if config.file_filter and not config.file_filter(path):
            return True

        if config.skip_existing:
            file_hash = self._get_file_hash(path)
            if file_hash in self._state.processed_files:
                return True

        return False

    def _process_file(self, path: Path) -> ProcessingResult:
        """Process a single file.

        Args:
            path: Path to the file.

        Returns:
            Processing result.
        """
        start_time = time.time()

        try:
            song = self.process_func(path)
            duration_ms = (time.time() - start_time) * 1000

            if song is None:
                return ProcessingResult(
                    path=path,
                    success=False,
                    duration_ms=duration_ms,
                    error="Processing returned None",
                )

            return ProcessingResult(
                path=path,
                success=True,
                song_id=song.song_id,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.exception(f"Error processing {path}: {e}")
            return ProcessingResult(
                path=path,
                success=False,
                duration_ms=duration_ms,
                error=str(e),
            )

    def _update_progress(self, result: ProcessingResult, config: BatchConfig) -> None:
        """Update progress after processing a file.

        Args:
            result: Processing result.
            config: Batch configuration.
        """
        self._progress.processed += 1

        if result.success:
            self._progress.succeeded += 1
            # Mark as processed
            file_hash = self._get_file_hash(result.path)
            self._state.processed_files.add(file_hash)
        else:
            self._progress.failed += 1

        # Update timing
        self._progress.elapsed_ms = (time.time() - self._progress.start_time) * 1000

        # Estimate remaining time
        if self._progress.processed > 0:
            avg_time = self._progress.elapsed_ms / self._progress.processed
            remaining = self._progress.total - self._progress.processed
            self._progress.estimated_remaining_ms = avg_time * remaining

        # Callback
        if config.on_file_complete:
            config.on_file_complete(result)

        if config.on_progress:
            config.on_progress(self._progress)

        # Save checkpoint periodically
        if (
            self._progress.processed % config.checkpoint_interval == 0
            and self._state.checkpoint_path
        ):
            self._save_checkpoint()

    def process_files(
        self,
        files: list[Path],
        config: BatchConfig | None = None,
        checkpoint_path: Path | None = None,
    ) -> list[ProcessingResult]:
        """Process a list of files.

        Args:
            files: List of file paths to process.
            config: Batch configuration.
            checkpoint_path: Optional path to checkpoint file.

        Returns:
            List of processing results.
        """
        config = config or BatchConfig()
        self._stop_requested = False

        # Load checkpoint if resuming
        if config.resume and checkpoint_path:
            self._load_checkpoint(checkpoint_path)

        # Filter files
        files_to_process = []
        for path in files:
            if self._should_skip(path, config):
                self._progress.skipped += 1
            else:
                files_to_process.append(path)

        # Initialize progress
        self._progress = BatchProgress(
            total=len(files_to_process),
            skipped=self._progress.skipped,
            start_time=time.time(),
        )

        if config.on_progress:
            config.on_progress(self._progress)

        results: list[ProcessingResult] = []

        # Process with thread pool
        if config.workers > 1:
            results = self._process_parallel(files_to_process, config)
        else:
            results = self._process_sequential(files_to_process, config)

        # Final checkpoint
        if checkpoint_path:
            self._save_checkpoint()

        return results

    def _process_sequential(
        self,
        files: list[Path],
        config: BatchConfig,
    ) -> list[ProcessingResult]:
        """Process files sequentially.

        Args:
            files: Files to process.
            config: Batch configuration.

        Returns:
            Processing results.
        """
        results: list[ProcessingResult] = []

        for path in files:
            if self._stop_requested:
                break

            self._progress.current_file = str(path)
            result = self._process_file(path)
            results.append(result)
            self._update_progress(result, config)

        return results

    def _process_parallel(
        self,
        files: list[Path],
        config: BatchConfig,
    ) -> list[ProcessingResult]:
        """Process files in parallel.

        Args:
            files: Files to process.
            config: Batch configuration.

        Returns:
            Processing results.
        """
        results: list[ProcessingResult] = []

        with ThreadPoolExecutor(max_workers=config.workers) as executor:
            # Submit all tasks
            future_to_path = {
                executor.submit(self._process_file, path): path
                for path in files
            }

            # Collect results as they complete
            for future in as_completed(future_to_path):
                if self._stop_requested:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                path = future_to_path[future]
                self._progress.current_file = str(path)

                try:
                    result = future.result()
                except Exception as e:
                    result = ProcessingResult(
                        path=path,
                        success=False,
                        error=str(e),
                    )

                results.append(result)
                self._update_progress(result, config)

        return results

    def process_directory(
        self,
        directory: Path,
        config: BatchConfig | None = None,
        recursive: bool = True,
        extensions: tuple[str, ...] = (".mid", ".midi"),
    ) -> list[ProcessingResult]:
        """Process all MIDI files in a directory.

        Args:
            directory: Directory to scan.
            config: Batch configuration.
            recursive: Whether to scan recursively.
            extensions: File extensions to include.

        Returns:
            List of processing results.
        """
        # Find all MIDI files
        files: list[Path] = []

        if recursive:
            for ext in extensions:
                files.extend(directory.rglob(f"*{ext}"))
        else:
            for ext in extensions:
                files.extend(directory.glob(f"*{ext}"))

        # Sort for consistent ordering
        files = sorted(set(files))

        # Set up checkpoint in directory
        checkpoint_path = directory / ".midi_analyzer_checkpoint"

        return self.process_files(files, config, checkpoint_path)

    def stop(self) -> None:
        """Request processing to stop."""
        self._stop_requested = True

    def get_progress(self) -> BatchProgress:
        """Get current progress.

        Returns:
            Current progress information.
        """
        return self._progress


def create_simple_processor(
    parse_func: Callable[[Path], Song | None],
) -> BatchProcessor:
    """Create a simple batch processor with default settings.

    Args:
        parse_func: Function to parse a MIDI file.

    Returns:
        Configured batch processor.
    """
    return BatchProcessor(process_func=parse_func)


def process_directory_simple(
    directory: Path,
    parse_func: Callable[[Path], Song | None],
    workers: int = 4,
    on_progress: Callable[[BatchProgress], None] | None = None,
) -> list[ProcessingResult]:
    """Simple function to process a directory of MIDI files.

    Args:
        directory: Directory containing MIDI files.
        parse_func: Function to parse a single file.
        workers: Number of parallel workers.
        on_progress: Optional progress callback.

    Returns:
        List of processing results.
    """
    processor = BatchProcessor(process_func=parse_func)
    config = BatchConfig(
        workers=workers,
        on_progress=on_progress,
    )
    return processor.process_directory(directory, config)
