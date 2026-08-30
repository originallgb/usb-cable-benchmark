"""Tests for LinkChecker."""

import subprocess
import pytest
from src.usb_tester.adb_controller import ADBController
from src.usb_tester.link_checker import LinkChecker, LinkInfo


def test_check_android_link_sysfs_superspeed():
    def runner(cmd, **kwargs):
        # First shell command checks sysfs candidates
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="super-speed\n", stderr="")

    adb = ADBController(runner=runner)
    checker = LinkChecker(adb)
    link = checker.check_android_link()

    assert link.raw_speed == "super-speed"
    assert link.speed_mbps == 5000.0
    assert link.is_superspeed is True
    assert "SuperSpeed (5 Gbps)" in link.description


def test_check_android_link_sysfs_highspeed():
    def runner(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="high-speed\n", stderr="")

    adb = ADBController(runner=runner)
    checker = LinkChecker(adb)
    link = checker.check_android_link()

    assert link.raw_speed == "high-speed"
    assert link.speed_mbps == 480.0
    assert link.is_superspeed is False


def test_check_android_link_dumpsys_fallback():
    dumpsys_out = (
        "USB Manager State:\n"
        "  mCurrentFunctions: midi,adb\n"
        "  USB Port Status:\n"
        "    current_speed: super-speed\n"
        "    power_role: sink\n"
    )

    def runner(cmd, **kwargs):
        cmd_str = " ".join(cmd)
        if "cat /sys" in cmd_str or "for p in" in cmd_str:
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")
        elif "dumpsys usb" in cmd_str:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=dumpsys_out, stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    adb = ADBController(runner=runner)
    checker = LinkChecker(adb)
    link = checker.check_android_link()

    assert link.is_superspeed is True
    assert link.speed_mbps == 5000.0
