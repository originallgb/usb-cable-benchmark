# USB Cable Benchmark & Diagnostic Tool

A non-destructive Python-based diagnostic utility and Antigravity skill to benchmark physical USB cables using Android ADB and a connected device (e.g., Pixel 7, Pixel 3a).

## Features

- **Non-Destructive RAM-to-RAM Throughput**: Streams in-memory synthetic buffers into `cat > /dev/null` on the Android device via `adb exec-in`, eliminating any NAND flash wear.
- **Physical Link Detection**: Queries Android kernel sysfs nodes (`/sys/devices/platform/soc/*.dwc3/gadget/speed`, `/sys/class/android_usb/android0/speed`, `/sys/class/udc/*/current_speed`) and Android `dumpsys usb`.
- **Host Controller Negotiation**: Checks Windows USB controller connection (`Get-PnpDevice -Class USB`) to detect xHCI SuperSpeed vs EHCI High-Speed ports.
- **Hardware Bottleneck Warning**: Detects device models (e.g., Pixel 3a USB 2.0 limitation vs Pixel 7 USB 3.2 Gen 1) to warn if the phone or host is the limiting factor.
- **Real-Time Battery & Power Monitoring**: Inspects `dumpsys battery` for voltage (mV), current (µA), and instantaneous power draw (W).
- **Intelligent Cable Classifier**: Evaluates measured throughput against physical layer negotiation to categorize cables (`Charge-Only`, `USB 2.0 High-Speed 480Mbps`, `USB 3.1 Gen 1 SuperSpeed 5Gbps`, `USB 3.1 Gen 2 SuperSpeed+ 10Gbps`, or `Degraded / High Packet Loss`).
- **Antigravity Skill Ready**: Preconfigured `.antigravity/skills/usb_tester/` for AI pair programming agents.

## Installation

Requires Python >= 3.10 and `adb` in PATH.

```powershell
uv venv
.venv\Scripts\activate
uv pip install -e ".[dev]"
```

## CLI Usage

Run full benchmark:
```powershell
python -m src.usb_tester.cli
```

Custom test size (e.g. 512 MB) and iterations:
```powershell
python -m src.usb_tester.cli --size-mb 512 --iterations 5
```

JSON output for agent / automation:
```powershell
python -m src.usb_tester.cli --json-output
```
