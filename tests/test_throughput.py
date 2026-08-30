"""Tests for ThroughputBenchmark."""

from unittest.mock import MagicMock, patch
import pytest
from src.usb_tester.adb_controller import ADBController
from src.usb_tester.throughput import SingleRunResult, ThroughputBenchmark, ThroughputResult


def test_throughput_aggregation():
    adb = ADBController()
    bench = ThroughputBenchmark(adb)

    runs = [
        SingleRunResult(
            iteration=1,
            bytes_transferred=1024 * 1024 * 100,
            duration_seconds=1.0,
            speed_mb_s=100.0,
            speed_gbps=0.838,
            speed_mbps=838.8,
            success=True,
        ),
        SingleRunResult(
            iteration=2,
            bytes_transferred=1024 * 1024 * 100,
            duration_seconds=0.5,
            speed_mb_s=200.0,
            speed_gbps=1.677,
            speed_mbps=1677.7,
            success=True,
        ),
    ]

    with patch.object(bench, "run_single_test", side_effect=runs):
        result = bench.benchmark(size_mb=100, iterations=2)

        assert result.iterations == 2
        assert result.all_successful is True
        assert result.mean_speed_mb_s == 150.0
        assert result.min_speed_mb_s == 100.0
        assert result.max_speed_mb_s == 200.0
        assert result.median_speed_mb_s == 150.0
        assert result.stdev_speed_mb_s > 0


def test_throughput_single_run_mock_popen():
    adb = ADBController()
    bench = ThroughputBenchmark(adb, chunk_size_bytes=64 * 1024)

    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    mock_proc.returncode = 0
    mock_proc.wait.return_value = None

    with patch("subprocess.Popen", return_value=mock_proc):
        with patch("time.perf_counter", side_effect=[1.0, 1.0, 1.0, 1.1, 1.1, 1.1]):
            res = bench.run_single_test(size_mb=1, iteration_index=1)
            assert res.success is True
            assert res.bytes_transferred == 1024 * 1024
            assert res.speed_mb_s > 0
