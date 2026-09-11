# USB Cable Benchmark & Diagnostic Tool

> *Non-destructive physical USB cable characterization via Android ADB.*

A diagnostic utility that measures memory-to-memory throughput, physical link layer negotiation, and power delivery across USB cables using an Android device—without writing a single byte to NAND flash storage.

---

## The Problem: Benchmarking Without Flash Wear

Traditional cable testing via mobile devices relies on file transfer utilities or `adb push`, which write multi-gigabyte payloads to the device's internal storage (`/sdcard/`). This approach introduces two critical flaws:

1. **Premature NAND Degradation**: Repeatedly pushing test files rapidly burns flash write cycles and degrades device storage endurance.
2. **Artificial Throughput Caps**: The benchmark measures the phone's NAND write speed and storage controller bottlenecks rather than the actual physical bandwidth of the cable.

### The Solution: Direct RAM-to-RAM Streaming

`usb-cable-benchmark` bypasses the mobile filesystem entirely. By piping in-memory synthetic buffers directly over ADB into `/dev/null` on the Android device:

```text
Host Memory (RAM) ──[ USB Cable ]──> ADB Daemon ──> cat > /dev/null (Device RAM)
```

No data touches persistent flash. Testing runs at line rate, bound only by the physical cable connection, USB controllers, and ADB protocol overhead.

---

## Core Capabilities

- **Zero Flash Wear**: High-throughput memory-to-memory streaming via `adb exec-in "cat > /dev/null"`.
- **Physical Link Detection (PHY)**: Probes Android kernel sysfs gadget nodes (`/sys/devices/platform/soc/*.dwc3/gadget/speed`, `/sys/class/udc/*/current_speed`) and `dumpsys usb` to determine negotiated physical link rates.
- **Host Controller Cross-Referencing**: Inspects the host USB root hub and controller hierarchy to verify whether the PC port is xHCI (USB 3.x) or EHCI (USB 2.0).
- **Hardware Bottleneck Attribution**: Differentiates between a deficient cable and hardware-limited devices (e.g., Pixel 3a/4a/5a/6a/7a capped at USB 2.0 PHY speeds vs Pixel 7/8/9 with USB 3.x SuperSpeed).
- **Power Delivery Monitoring**: Queries real-time voltage ($V$), current draw ($mA$), and instantaneous power ($W$) via `dumpsys battery`.
- **Intelligent Cable Classification**: Assigns definitive cable grades backed by confidence scoring and actionable recommendations.

---

## Cable Classification Matrix

| Grade | Negotiated PHY | Typical Real-World Throughput | Characteristics & Diagnosis |
| :--- | :--- | :--- | :--- |
| **Charge-Only** | None / Dropped | $0\text{ MB/s}$ | Power lines intact; data lines broken, severed, or omitted. |
| **USB 2.0 High-Speed** | 480 Mbps | $35 \text{--} 43\text{ MB/s}$ | Standard 4-wire USB 2.0 data lines or limited by host/device PHY. |
| **USB 3.1 Gen 1 SuperSpeed** | 5 Gbps | $150 \text{--} 350+\text{ MB/s}$ | Differential SuperSpeed pairs functional; high-bandwidth verified. |
| **USB 3.1 Gen 2 SuperSpeed+** | 10 Gbps | $> 350\text{ MB/s}$ | Gen 2 negotiation active; low protocol latency. |
| **Degraded / High Packet Loss** | 5 Gbps (PHY) | $< 25\text{ MB/s}$ | PHY negotiated SuperSpeed, but signal fatigue or dirty pins cause massive retransmissions. |

---

## Installation

### Prerequisites
- Python 3.10 or higher
- Android Platform Tools (`adb`) installed and available in system `PATH`
- An Android device with **USB Debugging enabled**

```bash
git clone https://github.com/originallgb/usb-cable-benchmark.git
cd usb-cable-benchmark

# Using uv
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# Or using standard pip
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

---

## Usage

### Interactive Terminal Benchmark
Runs a 1024 MB transfer across 3 iterations with live progress bars and summary tables:

```bash
python -m src.usb_tester.cli
```

### Custom Test Parameters
Adjust payload size (in MB) and iteration count:

```bash
python -m src.usb_tester.cli --size-mb 512 --iterations 5
```

Target a specific device when multiple phones are attached:

```bash
python -m src.usb_tester.cli --device 28251FDH200001
```

### Offline Simulation Mode
Verify rendering and diagnostic logic without physical hardware attached:

```bash
python -m src.usb_tester.cli --dry-run
```

### Structured JSON Output
Generate machine-readable diagnostics for scripting, CI pipelines, or automated tool calls:

```bash
python -m src.usb_tester.cli --json-output
```

```json
{
  "device": {
    "serial": "28251FDH200001",
    "model": "Pixel 7",
    "manufacturer": "Google",
    "is_usb2_limited": false
  },
  "link": {
    "raw_speed": "super-speed",
    "speed_mbps": 5000.0,
    "description": "USB 3.0 / 3.1 Gen 1 SuperSpeed (5 Gbps)",
    "is_superspeed": true
  },
  "power": {
    "voltage_v": 4.18,
    "current_now_ma": 1450.0,
    "power_watts": 6.06,
    "charging_status": "Charging"
  },
  "throughput": {
    "total_size_mb": 1024,
    "iterations": 3,
    "mean_speed_mb_s": 287.5,
    "mean_speed_gbps": 2.41
  },
  "classification": {
    "grade": "USB 3.1 Gen 1 SuperSpeed 5Gbps",
    "quality_score": 90,
    "confidence_percent": 95,
    "summary_message": "Verified USB 3.0 / 3.1 Gen 1 SuperSpeed cable (5 Gbps capability)."
  }
}
```

---

## Running the Test Suite

```bash
uv run pytest -v
```

---

## License

This project is licensed under the [MIT License](LICENSE).
