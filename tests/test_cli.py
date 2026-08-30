"""Tests for CLI entrypoint."""

import json
from typer.testing import CliRunner
from src.usb_tester.cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Run USB cable benchmark and diagnostics using ADB" in result.output
    assert "--size-mb" in result.output
    assert "--iterations" in result.output
    assert "--json-output" in result.output


def test_cli_dry_run_rich():
    result = runner.invoke(app, ["--dry-run", "--size-mb", "64", "--iterations", "2"])
    assert result.exit_code == 0
    assert "USB CABLE BENCHMARK" in result.output
    assert "FINAL CABLE RATING" in result.output
    assert "Google Pixel 7" in result.output


def test_cli_dry_run_json():
    result = runner.invoke(app, ["--dry-run", "--json-output", "--size-mb", "64", "--iterations", "2"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["device"]["model"] == "Pixel 7"
    assert data["link"]["is_superspeed"] is True
    assert data["throughput"]["total_size_mb"] == 64
    assert data["throughput"]["iterations"] == 2
    assert "classification" in data
    assert data["classification"]["grade"] == "USB 3.1 Gen 1 SuperSpeed 5Gbps"
