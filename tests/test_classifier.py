"""Tests for CableClassifier."""

import pytest
from src.usb_tester.adb_controller import DeviceInfo
from src.usb_tester.classifier import CableClassifier, CableGrade
from src.usb_tester.link_checker import LinkInfo, USBHostInfo
from src.usb_tester.throughput import SingleRunResult, ThroughputResult


def make_throughput_result(mean_mb_s: float, all_success: bool = True) -> ThroughputResult:
    runs = [
        SingleRunResult(
            iteration=1,
            bytes_transferred=1024 * 1024 * 500,
            duration_seconds=500.0 / max(0.1, mean_mb_s),
            speed_mb_s=mean_mb_s,
            speed_gbps=(mean_mb_s * 8) / 1000.0,
            speed_mbps=mean_mb_s * 8,
            success=all_success,
        )
    ]
    return ThroughputResult(
        total_size_mb=500,
        iterations=1,
        runs=runs,
        mean_speed_mb_s=mean_mb_s,
        median_speed_mb_s=mean_mb_s,
        min_speed_mb_s=mean_mb_s,
        max_speed_mb_s=mean_mb_s,
        stdev_speed_mb_s=0.0,
        mean_speed_gbps=(mean_mb_s * 8) / 1000.0,
        mean_speed_mbps=mean_mb_s * 8,
        overall_duration_seconds=500.0 / max(0.1, mean_mb_s),
        all_successful=all_success,
    )


def test_classify_usb3_superspeed_pixel7():
    dev = DeviceInfo(serial="P7", state="device", model="Pixel 7", is_usb2_limited=False)
    link = LinkInfo(raw_speed="super-speed", speed_mbps=5000.0, description="SuperSpeed (5 Gbps)", is_superspeed=True)
    host = USBHostInfo(os_name="Windows", has_usb3_controller=True)
    tp = make_throughput_result(280.0)

    res = CableClassifier.classify(dev, link, host, tp)
    assert res.grade == CableGrade.USB_3_1_GEN_1_SUPERSPEED
    assert res.is_bottlenecked_by_device is False
    assert res.quality_score >= 85


def test_classify_usb2_pixel3a_bottleneck():
    dev = DeviceInfo(
        serial="P3A",
        state="device",
        model="Pixel 3a",
        is_usb2_limited=True,
        limitation_reason="Pixel 3a has a USB 2.0 PHY hardware limit.",
    )
    link = LinkInfo(raw_speed="high-speed", speed_mbps=480.0, description="High-Speed (480 Mbps)", is_superspeed=False)
    host = USBHostInfo(os_name="Windows", has_usb3_controller=True)
    tp = make_throughput_result(38.0)

    res = CableClassifier.classify(dev, link, host, tp)
    assert res.grade == CableGrade.USB_2_0_HIGH_SPEED
    assert res.is_bottlenecked_by_device is True
    assert "Phone Hardware Bottleneck" in res.bottleneck_description


def test_classify_degraded_superspeed():
    dev = DeviceInfo(serial="P7", state="device", model="Pixel 7", is_usb2_limited=False)
    link = LinkInfo(raw_speed="super-speed", speed_mbps=5000.0, description="SuperSpeed (5 Gbps)", is_superspeed=True)
    host = USBHostInfo(os_name="Windows", has_usb3_controller=True)
    tp = make_throughput_result(15.0)  # Unusually low speed despite SuperSpeed PHY

    res = CableClassifier.classify(dev, link, host, tp)
    assert res.grade == CableGrade.DEGRADED_OR_PACKET_LOSS
    assert res.quality_score < 50


def test_classify_charge_only():
    dev = DeviceInfo(serial="P7", state="device", model="Pixel 7", is_usb2_limited=False)
    link = LinkInfo(raw_speed="unknown", speed_mbps=0.0, description="Unknown", is_superspeed=False)
    host = USBHostInfo(os_name="Windows", has_usb3_controller=True)
    tp = make_throughput_result(0.0, all_success=False)

    res = CableClassifier.classify(dev, link, host, tp)
    assert res.grade == CableGrade.CHARGE_ONLY
    assert res.quality_score <= 15
