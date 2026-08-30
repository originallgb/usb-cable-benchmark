---
name: usb-cable-benchmark
description: Benchmark and diagnose physical USB cables using ADB and an Android device without writing to NAND flash. Measures RAM-to-RAM throughput, link negotiation, and power draw.
---

# USB Cable Benchmark Skill

This skill allows Antigravity agents to run non-destructive physical USB cable diagnostics using an attached Android phone (e.g., Pixel 7, Pixel 3a, Galaxy S-series).

## When to Use

- When the user wants to test or verify a USB-C / USB-A cable's data transfer capabilities.
- When distinguishing between Charge-Only, USB 2.0 High-Speed (480 Mbps), USB 3.1 Gen 1 SuperSpeed (5 Gbps), and USB 3.1 Gen 2 SuperSpeed+ (10 Gbps) cables.
- When diagnosing intermittent disconnections, degraded cables, or hardware bottlenecks.

## Execution Command

```powershell
python -m src.usb_tester.cli --json-output
```

Optional arguments:
- `--size-mb <int>`: Payload size in MB per iteration (default: 1024).
- `--iterations <int>`: Number of benchmark runs (default: 3).
- `--device <serial>`: Target specific ADB serial.
- `--skip-power`: Omit battery/power readings.
- `--mock` / `--dry-run`: Run offline simulation.
