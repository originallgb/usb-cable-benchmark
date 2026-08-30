"""Link Checker for detecting Android device PHY link speed and Windows host USB negotiation."""

from __future__ import annotations

import dataclasses
import json
import logging
import platform
import re
import subprocess
from typing import Any, Dict, List, Optional

from .adb_controller import ADBController

logger = logging.getLogger(__name__)

# Android kernel sysfs paths known across Qualcomm, Samsung Exynos, Google Tensor, MediaTek
SYSFS_SPEED_CANDIDATES = [
    # Google Tensor & Qualcomm DWC3 gadget paths
    "/sys/devices/platform/soc/*.dwc3/gadget/speed",
    "/sys/devices/platform/soc/*dwc3/gadget/speed",
    "/sys/devices/platform/*.dwc3/gadget/speed",
    "/sys/devices/platform/soc/*.usb/gadget/speed",
    # Universal Device Controller (UDC) current_speed
    "/sys/class/udc/*/current_speed",
    "/sys/class/udc/*/speed",
    # Legacy Android USB
    "/sys/class/android_usb/android0/speed",
    "/sys/devices/virtual/android_usb/android0/speed",
    "/sys/devices/platform/android_usb/speed",
]

SPEED_MAP = {
    "super-speed-plus": (10000, "USB 3.1 Gen 2 SuperSpeed+ (10 Gbps)"),
    "super-speed": (5000, "USB 3.0 / 3.1 Gen 1 SuperSpeed (5 Gbps)"),
    "superspeed": (5000, "USB 3.0 / 3.1 Gen 1 SuperSpeed (5 Gbps)"),
    "high-speed": (480, "USB 2.0 High-Speed (480 Mbps)"),
    "highspeed": (480, "USB 2.0 High-Speed (480 Mbps)"),
    "full-speed": (12, "USB 1.1 Full-Speed (12 Mbps)"),
    "fullspeed": (12, "USB 1.1 Full-Speed (12 Mbps)"),
    "low-speed": (1.5, "USB 1.0 Low-Speed (1.5 Mbps)"),
    "lowspeed": (1.5, "USB 1.0 Low-Speed (1.5 Mbps)"),
}


@dataclasses.dataclass
class LinkInfo:
    """Represents the negotiated physical link between device and host."""
    raw_speed: str = "unknown"
    speed_mbps: float = 0.0
    description: str = "Unknown Link Speed"
    source: str = "unknown"
    is_superspeed: bool = False
    details: Dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class USBHostInfo:
    """Information regarding the host computer's USB controller and connection."""
    os_name: str
    host_controllers: List[str] = dataclasses.field(default_factory=list)
    has_usb3_controller: bool = False
    connected_usb_devices: List[Dict[str, str]] = dataclasses.field(default_factory=list)
    raw_query_output: str = ""


class LinkChecker:
    """Checks negotiated USB link speed on both the Android device and the host machine."""

    def __init__(self, adb: ADBController):
        self.adb = adb

    def check_android_link(self) -> LinkInfo:
        """Inspects Android kernel sysfs nodes and dumpsys to determine PHY link speed."""
        # 1. Try sysfs paths via shell wildcard expansion
        sysfs_cmd = "cat " + " ".join(SYSFS_SPEED_CANDIDATES) + " 2>/dev/null"
        result = self.adb.run_adb(["shell", sysfs_cmd], timeout=8.0)
        
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.splitlines():
                raw = line.strip().lower()
                if raw in SPEED_MAP:
                    mbps, desc = SPEED_MAP[raw]
                    return LinkInfo(
                        raw_speed=raw,
                        speed_mbps=float(mbps),
                        description=desc,
                        source="sysfs",
                        is_superspeed=mbps >= 5000,
                        details={"sysfs_output": result.stdout.strip()},
                    )

        # 2. Iterate specific sysfs candidate searches with ls / cat if wildcard failed
        search_script = (
            "for p in /sys/class/udc/*/current_speed /sys/devices/platform/*dwc3*/gadget/speed "
            "/sys/class/android_usb/android0/speed; do "
            "if [ -f \"$p\" ]; then echo \"$p: $(cat $p)\"; fi; done"
        )
        res_search = self.adb.run_adb(["shell", search_script], timeout=8.0)
        if res_search.returncode == 0 and res_search.stdout.strip():
            for line in res_search.stdout.splitlines():
                line_lower = line.strip().lower()
                for key, (mbps, desc) in SPEED_MAP.items():
                    if key in line_lower:
                        return LinkInfo(
                            raw_speed=key,
                            speed_mbps=float(mbps),
                            description=desc,
                            source="udc/sysfs",
                            is_superspeed=mbps >= 5000,
                            details={"found_path": line.strip()},
                        )

        # 3. Fallback: inspect `dumpsys usb`
        dumpsys_res = self.adb.run_adb(["shell", "dumpsys", "usb"], timeout=10.0)
        if dumpsys_res.returncode == 0 and dumpsys_res.stdout.strip():
            link_info = self._parse_dumpsys_usb(dumpsys_res.stdout)
            if link_info.raw_speed != "unknown":
                return link_info

        # 4. Unknown fallback
        return LinkInfo(
            raw_speed="unknown",
            speed_mbps=0.0,
            description="Unable to determine PHY link from kernel sysfs or dumpsys",
            source="none",
            is_superspeed=False,
            details={"dumpsys_available": dumpsys_res.returncode == 0},
        )

    def _parse_dumpsys_usb(self, output: str) -> LinkInfo:
        """Parses `dumpsys usb` output for speed and port capability indicators."""
        out_lower = output.lower()

        # Look for explicit speed keys in dumpsys
        speed_match = re.search(r'(?:current_speed|link_speed|speed|negotiated\s*speed)\s*[:=]\s*([a-zA-Z0-9_-]+)', out_lower)
        if speed_match:
            raw = speed_match.group(1).strip()
            if raw in SPEED_MAP:
                mbps, desc = SPEED_MAP[raw]
                return LinkInfo(
                    raw_speed=raw,
                    speed_mbps=float(mbps),
                    description=desc,
                    source="dumpsys usb (speed property)",
                    is_superspeed=mbps >= 5000,
                    details={"matched_line": speed_match.group(0)},
                )

        # Check for SuperSpeed keywords in USB port status
        if "superspeed" in out_lower or "super_speed" in out_lower or "usb 3." in out_lower:
            return LinkInfo(
                raw_speed="super-speed",
                speed_mbps=5000.0,
                description="USB 3.0 / 3.1 Gen 1 SuperSpeed (5 Gbps)",
                source="dumpsys usb (keyword match)",
                is_superspeed=True,
                details={"snippet": "Found SuperSpeed marker in dumpsys"},
            )
        elif "highspeed" in out_lower or "high_speed" in out_lower or "high-speed" in out_lower or "usb 2.0" in out_lower:
            return LinkInfo(
                raw_speed="high-speed",
                speed_mbps=480.0,
                description="USB 2.0 High-Speed (480 Mbps)",
                source="dumpsys usb (keyword match)",
                is_superspeed=False,
                details={"snippet": "Found HighSpeed marker in dumpsys"},
            )

        return LinkInfo(
            raw_speed="unknown",
            speed_mbps=0.0,
            description="Unknown Link Speed (dumpsys usb inconclusive)",
            source="dumpsys usb",
            is_superspeed=False,
        )

    def check_host_usb(self) -> USBHostInfo:
        """Cross-references host-side Windows USB controllers and device enumeration."""
        os_system = platform.system()
        if os_system != "Windows":
            return USBHostInfo(os_name=os_system, host_controllers=[f"Non-Windows Host ({os_system})"])

        ps_cmd = (
            "Get-PnpDevice -Class USB -PresentOnly | "
            "Select-Object FriendlyName, InstanceId, Status | "
            "ConvertTo-Json -Compress"
        )

        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=12.0,
            )
            raw_out = res.stdout.strip()
            devices: List[Dict[str, str]] = []
            controllers: List[str] = []
            has_usb3 = False

            if res.returncode == 0 and raw_out:
                try:
                    data = json.loads(raw_out)
                    if isinstance(data, dict):
                        data = [data]
                    for item in data:
                        fname = str(item.get("FriendlyName") or "")
                        iid = str(item.get("InstanceId") or "")
                        status = str(item.get("Status") or "")
                        
                        devices.append({
                            "name": fname,
                            "instance_id": iid,
                            "status": status,
                        })
                        
                        # Identify host controllers
                        if "host controller" in fname.lower() or "xhci" in fname.lower() or "ehci" in fname.lower() or "root hub" in fname.lower():
                            controllers.append(fname)
                        if "xhci" in fname.lower() or "3.0" in fname or "3.1" in fname or "3.2" in fname or "usb 3" in fname.lower():
                            has_usb3 = True
                except json.JSONDecodeError:
                    controllers.append("PowerShell JSON parse fallback")

            return USBHostInfo(
                os_name=os_system,
                host_controllers=controllers,
                has_usb3_controller=has_usb3,
                connected_usb_devices=devices,
                raw_query_output=raw_out[:1000],
            )
        except Exception as err:
            logger.warning("Failed to query Windows host USB devices: %s", err)
            return USBHostInfo(
                os_name=os_system,
                host_controllers=[f"Query error: {err}"],
                has_usb3_controller=False,
            )
