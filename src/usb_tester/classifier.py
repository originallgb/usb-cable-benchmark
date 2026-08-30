"""Cable classification and bottleneck diagnostic engine."""

from __future__ import annotations

import dataclasses
import enum
from typing import List, Optional

from .adb_controller import DeviceInfo
from .link_checker import LinkInfo, USBHostInfo
from .power_monitor import BatteryInfo
from .throughput import ThroughputResult


class CableGrade(str, enum.Enum):
    """Definitive cable classification grades."""
    CHARGE_ONLY = "Charge-Only"
    USB_2_0_HIGH_SPEED = "USB 2.0 High-Speed 480Mbps"
    USB_3_1_GEN_1_SUPERSPEED = "USB 3.1 Gen 1 SuperSpeed 5Gbps"
    USB_3_1_GEN_2_SUPERSPEED_PLUS = "USB 3.1 Gen 2 SuperSpeed+ 10Gbps"
    DEGRADED_OR_PACKET_LOSS = "Degraded / High Packet Loss"
    UNKNOWN = "Unknown / Inconclusive"


@dataclasses.dataclass
class ClassificationResult:
    """Complete diagnostic assessment of the USB cable."""
    grade: CableGrade
    rating_display: str
    confidence_percent: int
    quality_score: int  # 0 to 100
    is_bottlenecked_by_device: bool
    is_bottlenecked_by_host: bool
    bottleneck_description: Optional[str]
    summary_message: str
    detailed_findings: List[str]
    recommendations: List[str]


class CableClassifier:
    """Evaluates throughput, link negotiation, and hardware limits to classify cables."""

    @staticmethod
    def classify(
        device: DeviceInfo,
        link: LinkInfo,
        host: USBHostInfo,
        throughput: ThroughputResult,
        power: Optional[BatteryInfo] = None,
    ) -> ClassificationResult:
        """Computes cable grade, quality score, bottleneck attribution, and recommendations."""
        findings: List[str] = []
        recommendations: List[str] = []
        
        is_phone_limited = device.is_usb2_limited
        is_host_usb2_only = not host.has_usb3_controller if host.host_controllers else False
        
        mean_speed = throughput.mean_speed_mb_s
        phy_mbps = link.speed_mbps

        # Check if throughput test completely failed
        if not throughput.all_successful and throughput.mean_speed_mb_s == 0:
            return ClassificationResult(
                grade=CableGrade.CHARGE_ONLY,
                rating_display="Charge-Only (No Reliable Data)",
                confidence_percent=95,
                quality_score=10,
                is_bottlenecked_by_device=False,
                is_bottlenecked_by_host=False,
                bottleneck_description="No data connectivity could be established over the cable.",
                summary_message="Cable functions for power/charging only or has broken data lines.",
                detailed_findings=["Throughput test failed with zero bytes transferred.", "ADB connection dropped or data stream timed out."],
                recommendations=["Replace the cable if data synchronization or high-speed transfer is required."],
            )

        # Check for Degraded / Packet Loss conditions
        # Condition A: Negotiated SuperSpeed (> 1000 Mbps) but throughput is sluggish (< 25 MB/s)
        if link.is_superspeed and mean_speed < 25.0:
            grade = CableGrade.DEGRADED_OR_PACKET_LOSS
            score = 35
            confidence = 90
            summary = "Cable negotiated SuperSpeed PHY but experienced severe data throttling / packet loss."
            findings.append(f"Negotiated PHY speed is {link.description}, but real throughput is only {mean_speed:.2f} MB/s.")
            findings.append("Likely signal degradation, dirty USB-C pins, or internal wire fatigue on SuperSpeed differential pairs.")
            recommendations.append("Clean USB-C connectors with contact cleaner or compressed air.")
            recommendations.append("Test with a different USB port directly on the motherboard (avoid unpowered hubs).")
            recommendations.append("If issues persist, replace the degraded cable.")
            return ClassificationResult(
                grade=grade,
                rating_display=grade.value,
                confidence_percent=confidence,
                quality_score=score,
                is_bottlenecked_by_device=False,
                is_bottlenecked_by_host=False,
                bottleneck_description="Severe packet loss or retransmissions on high-speed lines.",
                summary_message=summary,
                detailed_findings=findings,
                recommendations=recommendations,
            )

        # Condition B: High-Speed PHY negotiation but throughput is heavily degraded (< 12 MB/s on a clean device)
        if phy_mbps == 480 and mean_speed < 12.0 and not throughput.all_successful:
            grade = CableGrade.DEGRADED_OR_PACKET_LOSS
            score = 40
            confidence = 85
            summary = "USB 2.0 transfer rate is unusually degraded with communication errors."
            findings.append(f"High-Speed PHY negotiated but throughput averaged only {mean_speed:.2f} MB/s with failed runs.")
            recommendations.append("Inspect USB pins for physical damage or replace cable.")
            return ClassificationResult(
                grade=grade,
                rating_display=grade.value,
                confidence_percent=confidence,
                quality_score=score,
                is_bottlenecked_by_device=False,
                is_bottlenecked_by_host=False,
                bottleneck_description="Substandard transfer speed and error rate on USB 2.0 lines.",
                summary_message=summary,
                detailed_findings=findings,
                recommendations=recommendations,
            )

        # Condition C: SuperSpeed+ 10Gbps
        if link.raw_speed == "super-speed-plus" or (link.is_superspeed and mean_speed >= 350.0):
            grade = CableGrade.USB_3_1_GEN_2_SUPERSPEED_PLUS
            score = 98
            confidence = 95
            summary = "High-performance USB 3.1/3.2 Gen 2 SuperSpeed+ cable (10 Gbps capability)."
            findings.append(f"Negotiated link: {link.description}.")
            findings.append(f"Measured RAM-to-RAM throughput: {mean_speed:.2f} MB/s ({throughput.mean_speed_gbps:.3f} Gbps).")
            if power and power.power_watts > 0:
                findings.append(f"Active power delivery: {power.voltage_v:.2f} V @ {abs(power.current_now_ma):.1f} mA ({power.power_watts:.2f} W).")
            recommendations.append("Cable is optimal for ultra-fast data transfer and high-bandwidth tethering.")
            return ClassificationResult(
                grade=grade,
                rating_display=grade.value,
                confidence_percent=confidence,
                quality_score=score,
                is_bottlenecked_by_device=False,
                is_bottlenecked_by_host=False,
                bottleneck_description=None,
                summary_message=summary,
                detailed_findings=findings,
                recommendations=recommendations,
            )

        # Condition D: SuperSpeed 5Gbps
        if link.is_superspeed or mean_speed >= 60.0:
            grade = CableGrade.USB_3_1_GEN_1_SUPERSPEED
            score = 90
            confidence = 95
            summary = "Verified USB 3.0 / 3.1 Gen 1 SuperSpeed cable (5 Gbps capability)."
            findings.append(f"Negotiated link: {link.description}.")
            findings.append(f"Measured RAM-to-RAM throughput: {mean_speed:.2f} MB/s ({throughput.mean_speed_mbps:.1f} Mbps).")
            if is_phone_limited:
                findings.append(f"Note: Connected device ({device.model}) is reported as USB 2.0 limited, but SuperSpeed negotiation was confirmed.")
            recommendations.append("Cable provides excellent high-speed transfer speeds.")
            return ClassificationResult(
                grade=grade,
                rating_display=grade.value,
                confidence_percent=confidence,
                quality_score=score,
                is_bottlenecked_by_device=False,
                is_bottlenecked_by_host=False,
                bottleneck_description=None,
                summary_message=summary,
                detailed_findings=findings,
                recommendations=recommendations,
            )

        # Condition E: USB 2.0 High-Speed
        # Check if limited by phone or host
        bottleneck_desc = None
        if is_phone_limited:
            bottleneck_desc = f"Phone Hardware Bottleneck: {device.manufacturer} {device.model} ({device.limitation_reason})"
            findings.append(f"Device limitation: {device.limitation_reason}")
            recommendations.append(
                f"To test if this cable supports SuperSpeed (5Gbps/10Gbps), connect a USB 3.x capable phone (e.g. Pixel 7/8/9, Galaxy S-series) or external SSD."
            )
        elif is_host_usb2_only:
            bottleneck_desc = "Host PC Bottleneck: Host USB port or controller is USB 2.0 EHCI."
            findings.append("Host PC appears to lack USB 3.x xHCI controller on this port.")
            recommendations.append("Connect cable to a blue / SS-marked USB 3.0+ port on your computer.")

        grade = CableGrade.USB_2_0_HIGH_SPEED
        score = 75 if not is_phone_limited else 85
        confidence = 90 if not is_phone_limited else 80
        summary = "Standard USB 2.0 High-Speed cable (480 Mbps max theoretical)."

        findings.append(f"Negotiated link: {link.description}.")
        findings.append(f"Measured RAM-to-RAM throughput: {mean_speed:.2f} MB/s ({throughput.mean_speed_mbps:.1f} Mbps).")
        if 30.0 <= mean_speed <= 48.0:
            findings.append("Throughput matches expected USB 2.0 maximum real-world bandwidth (35-43 MB/s).")

        return ClassificationResult(
            grade=grade,
            rating_display=grade.value,
            confidence_percent=confidence,
            quality_score=score,
            is_bottlenecked_by_device=is_phone_limited,
            is_bottlenecked_by_host=is_host_usb2_only,
            bottleneck_description=bottleneck_desc,
            summary_message=summary,
            detailed_findings=findings,
            recommendations=recommendations,
        )
