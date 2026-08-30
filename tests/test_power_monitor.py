"""Tests for PowerMonitor."""

import subprocess
import pytest
from src.usb_tester.adb_controller import ADBController
from src.usb_tester.power_monitor import PowerMonitor


def test_power_monitor_dumpsys_parsing():
    dumpsys_battery_output = (
        "Current Battery Service state:\n"
        "  AC powered: false\n"
        "  USB powered: true\n"
        "  Wireless powered: false\n"
        "  Max charging current: 1500000\n"
        "  Max charging voltage: 5000000\n"
        "  status: 2\n"
        "  health: 2\n"
        "  present: true\n"
        "  level: 82\n"
        "  scale: 100\n"
        "  voltage: 4120\n"
        "  temperature: 285\n"
        "  technology: Li-ion\n"
        "  current now: 1250000\n"
    )

    def runner(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=dumpsys_battery_output, stderr="")

    adb = ADBController(runner=runner)
    monitor = PowerMonitor(adb)
    info = monitor.get_battery_info()

    assert info.voltage_mv == 4120
    assert info.voltage_v == 4.12
    assert info.current_now_ua == 1250000
    assert info.current_now_ma == 1250.0
    assert info.current_now_a == 1.25
    assert round(info.power_watts, 2) == 5.15
    assert info.is_charging is True
    assert info.charging_status == "Charging"
    assert info.charge_source == "USB Port"
    assert info.level_percent == 82
    assert info.health == "Good"
    assert info.temperature_c == 28.5
