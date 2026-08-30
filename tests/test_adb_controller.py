"""Tests for ADBController."""

import subprocess
import pytest
from src.usb_tester.adb_controller import ADBController, DeviceInfo


def make_mock_runner(stdout: str = "", returncode: int = 0, stderr: str = ""):
    def runner(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=returncode, stdout=stdout, stderr=stderr)
    return runner


def test_check_adb_installed():
    adb = ADBController(runner=make_mock_runner(stdout="Android Debug Bridge version 1.0.41\n", returncode=0))
    assert adb.check_adb_installed() is True

    adb_fail = ADBController(runner=make_mock_runner(returncode=1))
    assert adb_fail.check_adb_installed() is False


def test_list_devices():
    output = (
        "List of devices attached\n"
        "28251FDH200001         device product:panther model:Pixel_7 device:panther\n"
        "9A081FFAZ00002         unauthorized\n"
    )
    adb = ADBController(runner=make_mock_runner(stdout=output, returncode=0))
    devices = adb.list_devices()
    assert len(devices) == 2
    assert devices[0]["serial"] == "28251FDH200001"
    assert devices[0]["state"] == "device"
    assert devices[1]["state"] == "unauthorized"


def test_inspect_device_pixel_7():
    getprop_output = (
        "[ro.product.model]: [Pixel 7]\n"
        "[ro.product.manufacturer]: [Google]\n"
        "[ro.product.brand]: [google]\n"
        "[ro.product.device]: [panther]\n"
        "[ro.build.version.release]: [14]\n"
        "[ro.build.version.sdk]: [34]\n"
        "[ro.soc.model]: [Tensor G2]\n"
    )

    def dispatch_runner(cmd, **kwargs):
        if "devices" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="28251FDH200001 device\n", stderr="")
        elif "getprop" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=getprop_output, stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    adb = ADBController(runner=dispatch_runner)
    info = adb.inspect_device()

    assert info.serial == "28251FDH200001"
    assert info.model == "Pixel 7"
    assert info.manufacturer == "Google"
    assert info.is_usb2_limited is False
    assert info.limitation_reason is None


def test_inspect_device_pixel_3a_usb2_warning():
    getprop_output = (
        "[ro.product.model]: [Pixel 3a]\n"
        "[ro.product.manufacturer]: [Google]\n"
        "[ro.product.device]: [sargo]\n"
        "[ro.build.version.release]: [12]\n"
    )

    def dispatch_runner(cmd, **kwargs):
        if "devices" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="95AY0BND7 device\n", stderr="")
        elif "getprop" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=getprop_output, stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    adb = ADBController(runner=dispatch_runner)
    info = adb.inspect_device()

    assert info.model == "Pixel 3a"
    assert info.is_usb2_limited is True
    assert "Pixel 3a" in info.limitation_reason
