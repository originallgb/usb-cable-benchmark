"""Power and battery monitoring module using Android dumpsys battery."""

from __future__ import annotations

import dataclasses
import logging
import re
from typing import Any, Dict, Optional

from .adb_controller import ADBController

logger = logging.getLogger(__name__)

STATUS_MAP = {
    1: "Unknown",
    2: "Charging",
    3: "Discharging",
    4: "Not charging",
    5: "Full",
}

HEALTH_MAP = {
    1: "Unknown",
    2: "Good",
    3: "Overheat",
    4: "Dead",
    5: "Over voltage",
    6: "Unspecified failure",
    7: "Cold",
}


@dataclasses.dataclass
class BatteryInfo:
    """Real-time battery and power metrics from the device."""
    voltage_mv: int = 0
    voltage_v: float = 0.0
    current_now_ua: int = 0
    current_now_ma: float = 0.0
    current_now_a: float = 0.0
    power_watts: float = 0.0
    charging_status: str = "Unknown"
    charge_source: str = "Unknown"
    level_percent: int = 0
    health: str = "Unknown"
    temperature_c: float = 0.0
    is_charging: bool = False
    raw_properties: Dict[str, Any] = dataclasses.field(default_factory=dict)


class PowerMonitor:
    """Monitors device power delivery, voltage, and current draw."""

    def __init__(self, adb: ADBController):
        self.adb = adb

    def get_battery_info(self) -> BatteryInfo:
        """Queries `adb shell dumpsys battery` and calculates real-time power metrics."""
        result = self.adb.run_adb(["shell", "dumpsys", "battery"], timeout=8.0)
        if result.returncode != 0 or not result.stdout.strip():
            logger.warning("Failed to query dumpsys battery: code %s", result.returncode)
            return BatteryInfo()

        raw_props: Dict[str, str] = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if ":" in line:
                key, val = line.split(":", 1)
                raw_props[key.strip().lower()] = val.strip()

        # Parse Voltage (standard unit: mV)
        voltage_mv = 0
        if "voltage" in raw_props:
            try:
                voltage_mv = int(raw_props["voltage"])
            except ValueError:
                pass
        voltage_v = voltage_mv / 1000.0 if voltage_mv > 0 else 0.0

        # Parse Current (Android devices typically report in µA, sometimes mA)
        current_now_ua = 0
        current_raw = (
            raw_props.get("current now")
            or raw_props.get("current_now")
            or raw_props.get("battery_current")
        )
        if current_raw:
            try:
                val = int(current_raw)
                # If absolute value is > 50000, it's almost certainly microamperes (µA)
                if abs(val) > 50000 or abs(val) > 10000:
                    current_now_ua = val
                else:
                    # Reported directly in mA
                    current_now_ua = val * 1000
            except ValueError:
                pass
        else:
            # Try reading /sys/class/power_supply/battery/current_now as backup
            sysfs_res = self.adb.run_adb(
                ["shell", "cat /sys/class/power_supply/battery/current_now 2>/dev/null"],
                timeout=5.0,
            )
            if sysfs_res.returncode == 0 and sysfs_res.stdout.strip().lstrip("-").isdigit():
                try:
                    val = int(sysfs_res.stdout.strip())
                    current_now_ua = val if abs(val) > 10000 else val * 1000
                except ValueError:
                    pass

        current_now_ma = current_now_ua / 1000.0
        current_now_a = current_now_ma / 1000.0
        power_watts = abs(voltage_v * current_now_a)

        # Parse Status & Source
        status_code = int(raw_props.get("status", 0)) if raw_props.get("status", "").isdigit() else 0
        charging_status = STATUS_MAP.get(status_code, "Unknown")
        is_charging = status_code == 2

        charge_source = "Battery"
        if raw_props.get("usb powered", "").lower() == "true":
            charge_source = "USB Port"
        elif raw_props.get("ac powered", "").lower() == "true":
            charge_source = "AC Charger"
        elif raw_props.get("wireless powered", "").lower() == "true":
            charge_source = "Wireless"
        elif raw_props.get("dock powered", "").lower() == "true":
            charge_source = "Dock"

        # Level
        level_percent = int(raw_props.get("level", 0)) if raw_props.get("level", "").isdigit() else 0

        # Health
        health_code = int(raw_props.get("health", 0)) if raw_props.get("health", "").isdigit() else 0
        health = HEALTH_MAP.get(health_code, "Unknown")

        # Temperature (tenths of Celsius)
        temperature_c = 0.0
        if "temperature" in raw_props and raw_props["temperature"].isdigit():
            temperature_c = int(raw_props["temperature"]) / 10.0

        return BatteryInfo(
            voltage_mv=voltage_mv,
            voltage_v=voltage_v,
            current_now_ua=current_now_ua,
            current_now_ma=current_now_ma,
            current_now_a=current_now_a,
            power_watts=power_watts,
            charging_status=charging_status,
            charge_source=charge_source,
            level_percent=level_percent,
            health=health,
            temperature_c=temperature_c,
            is_charging=is_charging,
            raw_properties=raw_props,
        )
