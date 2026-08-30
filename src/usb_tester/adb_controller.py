"""ADB Controller for managing device connections and querying hardware properties."""

from __future__ import annotations

import dataclasses
import logging
import shutil
import subprocess
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Known devices that are hardware-limited to USB 2.0 High-Speed (480 Mbps) despite USB-C
KNOWN_USB2_ONLY_MODELS = {
    # Google Pixel 'a' series
    "pixel 3a": "Google Pixel 3a has a USB 2.0 Type-C hardware PHY controller (max 480 Mbps).",
    "pixel 3a xl": "Google Pixel 3a XL has a USB 2.0 Type-C hardware PHY controller (max 480 Mbps).",
    "pixel 4a": "Google Pixel 4a (non-5G) is hardware-limited to USB 2.0 (max 480 Mbps).",
    "pixel 5a": "Google Pixel 5a is hardware-limited to USB 2.0 (max 480 Mbps).",
    "pixel 6a": "Google Pixel 6a is hardware-limited to USB 2.0 (max 480 Mbps).",
    "pixel 7a": "Google Pixel 7a is hardware-limited to USB 2.0 (max 480 Mbps).",
    "pixel 8a": "Google Pixel 8a is hardware-limited to USB 2.0 (max 480 Mbps).",
    # Apple (when accessed via ADB or emulated/tools)
    "iphone 15": "Apple iPhone 15 base models are hardware-limited to USB 2.0 (max 480 Mbps).",
    "iphone 15 plus": "Apple iPhone 15 Plus is hardware-limited to USB 2.0 (max 480 Mbps).",
    # Samsung A-series / generic budget models
    "galaxy a": "Most Samsung Galaxy A-series models are hardware-limited to USB 2.0.",
    "moto g": "Most Motorola Moto G series models are hardware-limited to USB 2.0.",
    "redmi": "Most Xiaomi Redmi series models are hardware-limited to USB 2.0.",
}

# Known devices known to support USB 3.x SuperSpeed (5Gbps / 10Gbps)
KNOWN_USB3_CAPABLE_MODELS = {
    "pixel 2": "USB 3.1 Gen 1 (5 Gbps)",
    "pixel 3": "USB 3.1 Gen 1 (5 Gbps)",
    "pixel 4": "USB 3.1 Gen 1 (5 Gbps)",
    "pixel 6": "USB 3.1 Gen 1 (5 Gbps)",
    "pixel 6 pro": "USB 3.1 Gen 1 (5 Gbps)",
    "pixel 7": "USB 3.2 Gen 1 (5 Gbps)",
    "pixel 7 pro": "USB 3.2 Gen 1 (5 Gbps)",
    "pixel 8": "USB 3.2 Gen 1 (5 Gbps)",
    "pixel 8 pro": "USB 3.2 Gen 2 (10 Gbps)",
    "pixel 9": "USB 3.2 Gen 1 (5 Gbps)",
    "pixel 9 pro": "USB 3.2 Gen 2 (10 Gbps)",
    "galaxy s": "Samsung Galaxy S series flagships support USB 3.2 SuperSpeed.",
}


@dataclasses.dataclass
class DeviceInfo:
    """Information about a connected Android device."""
    serial: str
    state: str
    model: str = "Unknown"
    manufacturer: str = "Unknown"
    brand: str = "Unknown"
    device_codename: str = "Unknown"
    android_version: str = "Unknown"
    sdk_version: str = "Unknown"
    soc_model: str = "Unknown"
    is_usb2_limited: bool = False
    limitation_reason: Optional[str] = None
    properties: Dict[str, str] = dataclasses.field(default_factory=dict)


class ADBController:
    """Manages ADB interactions and queries hardware metadata."""

    def __init__(
        self,
        serial: Optional[str] = None,
        adb_path: Optional[str] = None,
        runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
    ):
        self.serial = serial
        self.adb_path = adb_path or shutil.which("adb") or "adb"
        self._runner = runner or subprocess.run

    def run_adb(
        self,
        args: List[str],
        timeout: Optional[float] = 30.0,
        capture_output: bool = True,
        check: bool = False,
    ) -> subprocess.CompletedProcess:
        """Executes an ADB command and returns the completed process."""
        cmd = [self.adb_path]
        if self.serial:
            cmd.extend(["-s", self.serial])
        cmd.extend(args)

        try:
            return self._runner(
                cmd,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                check=check,
            )
        except subprocess.TimeoutExpired as err:
            logger.error("ADB command timed out after %s seconds: %s", timeout, cmd)
            raise TimeoutError(f"ADB command timed out: {' '.join(cmd)}") from err
        except FileNotFoundError as err:
            logger.error("ADB binary not found at %s", self.adb_path)
            raise RuntimeError(f"ADB executable not found at '{self.adb_path}'. Please install Android Platform Tools.") from err

    def check_adb_installed(self) -> bool:
        """Verifies if the ADB executable is available in PATH."""
        try:
            res = self.run_adb(["version"], timeout=5.0)
            return res.returncode == 0
        except Exception:
            return False

    def list_devices(self) -> List[Dict[str, str]]:
        """Lists attached devices via `adb devices -l`."""
        result = self.run_adb(["devices", "-l"], timeout=10.0)
        devices: List[Dict[str, str]] = []
        if result.returncode != 0:
            return devices

        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices attached") or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                serial = parts[0]
                state = parts[1]
                extra = " ".join(parts[2:]) if len(parts) > 2 else ""
                devices.append({
                    "serial": serial,
                    "state": state,
                    "extra": extra,
                })
        return devices

    def get_device_state(self) -> str:
        """Queries the connection state of the selected device."""
        try:
            result = self.run_adb(["get-state"], timeout=5.0)
            if result.returncode == 0:
                return result.stdout.strip()
            return "disconnected"
        except Exception:
            return "error"

    def get_properties(self) -> Dict[str, str]:
        """Fetches all system properties from the device via `adb shell getprop`."""
        result = self.run_adb(["shell", "getprop"], timeout=10.0)
        props: Dict[str, str] = {}
        if result.returncode != 0:
            return props

        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("[") and "]: [" in line:
                key, val = line.split("]: [", 1)
                clean_key = key.lstrip("[").strip()
                clean_val = val.rstrip("]").strip()
                props[clean_key] = clean_val
        return props

    def inspect_device(self) -> DeviceInfo:
        """Performs full hardware and status inspection of the connected device."""
        devices = self.list_devices()
        if not devices:
            raise ConnectionError("No Android device detected. Please connect an Android device via USB with USB Debugging enabled.")

        # Match device by serial or pick first online device
        target_serial = self.serial
        target_device = None
        if target_serial:
            for d in devices:
                if d["serial"] == target_serial:
                    target_device = d
                    break
            if not target_device:
                raise ConnectionError(f"Device with serial '{target_serial}' not found in attached devices.")
        else:
            online_devices = [d for d in devices if d["state"] == "device"]
            if not online_devices:
                raise ConnectionError(
                    f"Found devices but none are in 'device' state. Current devices: {devices}. Check device authorization."
                )
            target_device = online_devices[0]
            self.serial = target_device["serial"]

        state = target_device["state"]
        if state != "device":
            raise PermissionError(
                f"Device '{self.serial}' is in '{state}' state. Please check USB debugging authorization on the device screen."
            )

        props = self.get_properties()
        model = props.get("ro.product.model") or props.get("ro.product.vendor.model") or "Unknown"
        manufacturer = props.get("ro.product.manufacturer") or "Unknown"
        brand = props.get("ro.product.brand") or "Unknown"
        device_codename = props.get("ro.product.device") or props.get("ro.build.product") or "Unknown"
        android_version = props.get("ro.build.version.release") or "Unknown"
        sdk_version = props.get("ro.build.version.sdk") or "Unknown"
        soc_model = props.get("ro.soc.model") or props.get("ro.board.platform") or "Unknown"

        # Check for USB 2.0 limitation
        is_usb2_limited = False
        limitation_reason = None

        combined_name = f"{manufacturer} {model}".lower()
        model_lower = model.lower()

        for known_usb2, reason in KNOWN_USB2_ONLY_MODELS.items():
            if known_usb2 in model_lower or known_usb2 in combined_name:
                is_usb2_limited = True
                limitation_reason = reason
                break

        return DeviceInfo(
            serial=self.serial,
            state=state,
            model=model,
            manufacturer=manufacturer,
            brand=brand,
            device_codename=device_codename,
            android_version=android_version,
            sdk_version=sdk_version,
            soc_model=soc_model,
            is_usb2_limited=is_usb2_limited,
            limitation_reason=limitation_reason,
            properties=props,
        )
