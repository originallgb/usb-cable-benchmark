"""Throughput benchmark module for non-destructive RAM-to-RAM data transfer testing."""

from __future__ import annotations

import dataclasses
import logging
import statistics
import subprocess
import time
from typing import Callable, List, Optional

from .adb_controller import ADBController

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE_BYTES = 1024 * 1024  # 1 MB chunk
PROGRESS_CALLBACK_TYPE = Callable[[int, int, float], None]  # (bytes_written, total_bytes, current_speed_mb_s)


@dataclasses.dataclass
class SingleRunResult:
    """Result of a single iteration throughput measurement."""
    iteration: int
    bytes_transferred: int
    duration_seconds: float
    speed_mb_s: float
    speed_gbps: float
    speed_mbps: float
    success: bool
    error: Optional[str] = None


@dataclasses.dataclass
class ThroughputResult:
    """Aggregated results across multiple throughput benchmark iterations."""
    total_size_mb: int
    iterations: int
    runs: List[SingleRunResult]
    mean_speed_mb_s: float
    median_speed_mb_s: float
    min_speed_mb_s: float
    max_speed_mb_s: float
    stdev_speed_mb_s: float
    mean_speed_gbps: float
    mean_speed_mbps: float
    overall_duration_seconds: float
    all_successful: bool


class ThroughputBenchmark:
    """Benchmarks USB connection throughput without writing to flash storage."""

    def __init__(self, adb: ADBController, chunk_size_bytes: int = DEFAULT_CHUNK_SIZE_BYTES):
        self.adb = adb
        self.chunk_size_bytes = max(64 * 1024, chunk_size_bytes)
        # Pre-allocate synthetic pattern chunk to minimize CPU allocation overhead during streaming
        self._pattern_chunk = b"\xaa\x55\x00\xff" * (self.chunk_size_bytes // 4)

    def run_single_test(
        self,
        size_mb: int,
        iteration_index: int = 1,
        progress_cb: Optional[PROGRESS_CALLBACK_TYPE] = None,
        timeout: float = 300.0,
    ) -> SingleRunResult:
        """Streams synthetic data into Android `/dev/null` and measures real transfer speed."""
        total_bytes = size_mb * 1024 * 1024
        bytes_sent = 0

        cmd = [self.adb.adb_path]
        if self.adb.serial:
            cmd.extend(["-s", self.adb.serial])
        
        # Use exec-in to bypass PTY mangling and stream directly to /dev/null
        cmd.extend(["exec-in", "cat > /dev/null"])

        proc = None
        start_time = None
        end_time = None

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

            start_time = time.perf_counter()

            while bytes_sent < total_bytes:
                remaining = total_bytes - bytes_sent
                to_write = self._pattern_chunk if remaining >= self.chunk_size_bytes else self._pattern_chunk[:remaining]
                
                assert proc.stdin is not None
                proc.stdin.write(to_write)
                bytes_sent += len(to_write)

                if progress_cb and bytes_sent % (4 * 1024 * 1024) == 0:
                    current_elapsed = max(0.001, time.perf_counter() - start_time)
                    current_mb_s = (bytes_sent / (1024 * 1024)) / current_elapsed
                    progress_cb(bytes_sent, total_bytes, current_mb_s)

            # Close stdin and flush
            if proc.stdin:
                proc.stdin.flush()
                proc.stdin.close()

            proc.wait(timeout=max(10.0, total_bytes / (1024 * 1024 * 5)))  # at least 5 MB/s timeout baseline
            end_time = time.perf_counter()

            if proc.returncode != 0:
                stderr_text = proc.stderr.read().decode("utf-8", errors="ignore") if proc.stderr else ""
                return SingleRunResult(
                    iteration=iteration_index,
                    bytes_transferred=bytes_sent,
                    duration_seconds=max(0.001, (end_time or time.perf_counter()) - (start_time or time.perf_counter())),
                    speed_mb_s=0.0,
                    speed_gbps=0.0,
                    speed_mbps=0.0,
                    success=False,
                    error=f"Process exited with code {proc.returncode}: {stderr_text.strip()}",
                )

            duration = max(0.0001, end_time - start_time)
            speed_mb_s = (bytes_sent / (1024 * 1024)) / duration
            speed_mbps = (bytes_sent * 8) / (duration * 1_000_000)
            speed_gbps = speed_mbps / 1000.0

            if progress_cb:
                progress_cb(total_bytes, total_bytes, speed_mb_s)

            return SingleRunResult(
                iteration=iteration_index,
                bytes_transferred=bytes_sent,
                duration_seconds=duration,
                speed_mb_s=speed_mb_s,
                speed_gbps=speed_gbps,
                speed_mbps=speed_mbps,
                success=True,
            )

        except Exception as err:
            logger.error("Error during throughput benchmark iteration %s: %s", iteration_index, err)
            if proc and proc.poll() is None:
                proc.kill()
            current_elapsed = max(0.001, (time.perf_counter() - start_time) if start_time else 0.001)
            return SingleRunResult(
                iteration=iteration_index,
                bytes_transferred=bytes_sent,
                duration_seconds=current_elapsed,
                speed_mb_s=0.0,
                speed_gbps=0.0,
                speed_mbps=0.0,
                success=False,
                error=str(err),
            )

    def benchmark(
        self,
        size_mb: int = 1024,
        iterations: int = 3,
        run_start_cb: Optional[Callable[[int, int], None]] = None,
        progress_cb: Optional[PROGRESS_CALLBACK_TYPE] = None,
        run_finish_cb: Optional[Callable[[SingleRunResult], None]] = None,
    ) -> ThroughputResult:
        """Runs multiple benchmark iterations and aggregates performance statistics."""
        runs: List[SingleRunResult] = []
        overall_start = time.perf_counter()

        for i in range(1, iterations + 1):
            if run_start_cb:
                run_start_cb(i, iterations)

            res = self.run_single_test(
                size_mb=size_mb,
                iteration_index=i,
                progress_cb=progress_cb,
            )
            runs.append(res)

            if run_finish_cb:
                run_finish_cb(res)

        overall_duration = time.perf_counter() - overall_start
        successful_runs = [r for r in runs if r.success]

        if successful_runs:
            speeds = [r.speed_mb_s for r in successful_runs]
            mean_speed = statistics.mean(speeds)
            median_speed = statistics.median(speeds)
            min_speed = min(speeds)
            max_speed = max(speeds)
            stdev_speed = statistics.stdev(speeds) if len(speeds) > 1 else 0.0
            mean_mbps = mean_speed * (1024 * 1024 * 8) / 1_000_000
            mean_gbps = mean_mbps / 1000.0
        else:
            mean_speed = median_speed = min_speed = max_speed = stdev_speed = mean_mbps = mean_gbps = 0.0

        return ThroughputResult(
            total_size_mb=size_mb,
            iterations=iterations,
            runs=runs,
            mean_speed_mb_s=mean_speed,
            median_speed_mb_s=median_speed,
            min_speed_mb_s=min_speed,
            max_speed_mb_s=max_speed,
            stdev_speed_mb_s=stdev_speed,
            mean_speed_gbps=mean_gbps,
            mean_speed_mbps=mean_mbps,
            overall_duration_seconds=overall_duration,
            all_successful=(len(successful_runs) == len(runs) and len(runs) > 0),
        )
