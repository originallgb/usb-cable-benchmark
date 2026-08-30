"""Command-line interface and Rich terminal presentation for USB Cable Benchmark."""

from __future__ import annotations

import json
import sys
from typing import Optional

import typer
from rich import box
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TimeRemainingColumn, TransferSpeedColumn
from rich.table import Table
from rich.text import Text

from .adb_controller import ADBController, DeviceInfo
from .classifier import CableClassifier, CableGrade, ClassificationResult
from .link_checker import LinkChecker, LinkInfo, USBHostInfo
from .power_monitor import BatteryInfo, PowerMonitor
from .throughput import SingleRunResult, ThroughputBenchmark, ThroughputResult

app = typer.Typer(
    name="usb-tester",
    help="Benchmark and classify physical USB cables non-destructively using Android ADB.",
    add_completion=False,
)
console = Console()


def create_mock_data(size_mb: int, iterations: int) -> tuple[DeviceInfo, LinkInfo, USBHostInfo, ThroughputResult, BatteryInfo]:
    """Generates synthetic data for dry-run / mock testing mode."""
    device = DeviceInfo(
        serial="MOCK_PIXEL_7_001",
        state="device",
        model="Pixel 7",
        manufacturer="Google",
        brand="google",
        device_codename="panther",
        android_version="14",
        sdk_version="34",
        soc_model="Tensor G2",
        is_usb2_limited=False,
    )
    link = LinkInfo(
        raw_speed="super-speed",
        speed_mbps=5000.0,
        description="USB 3.0 / 3.1 Gen 1 SuperSpeed (5 Gbps)",
        source="sysfs",
        is_superspeed=True,
    )
    host = USBHostInfo(
        os_name="Windows",
        host_controllers=["Intel(R) USB 3.1 eXtensible Host Controller - 1.20 (Microsoft)"],
        has_usb3_controller=True,
    )
    runs = [
        SingleRunResult(
            iteration=i,
            bytes_transferred=size_mb * 1024 * 1024,
            duration_seconds=size_mb / 285.0,
            speed_mb_s=285.0 + (i * 2.5),
            speed_gbps=2.39,
            speed_mbps=2390.0,
            success=True,
        )
        for i in range(1, iterations + 1)
    ]
    throughput = ThroughputResult(
        total_size_mb=size_mb,
        iterations=iterations,
        runs=runs,
        mean_speed_mb_s=287.5,
        median_speed_mb_s=287.5,
        min_speed_mb_s=285.0,
        max_speed_mb_s=290.0,
        stdev_speed_mb_s=2.5,
        mean_speed_gbps=2.41,
        mean_speed_mbps=2411.7,
        overall_duration_seconds=sum(r.duration_seconds for r in runs),
        all_successful=True,
    )
    power = BatteryInfo(
        voltage_mv=4180,
        voltage_v=4.18,
        current_now_ua=1450000,
        current_now_ma=1450.0,
        current_now_a=1.45,
        power_watts=6.06,
        charging_status="Charging",
        charge_source="USB Port",
        level_percent=78,
        health="Good",
        temperature_c=29.4,
        is_charging=True,
    )
    return device, link, host, throughput, power


def print_rich_report(
    device: DeviceInfo,
    link: LinkInfo,
    host: USBHostInfo,
    throughput: ThroughputResult,
    power: Optional[BatteryInfo],
    result: ClassificationResult,
) -> None:
    """Renders formatted diagnostics, statistics, and verdict tables."""
    console.print()
    
    # Title Banner
    banner = Text("⚡ USB CABLE BENCHMARK & DIAGNOSTIC REPORT ⚡", style="bold cyan")
    console.print(Panel(Align.center(banner), border_style="cyan", box=box.ROUNDED))

    # Environment Summary Table
    env_table = Table(title="Hardware & Connection Environment", box=box.ROUNDED, expand=True)
    env_table.add_column("Component", style="bold yellow", width=22)
    env_table.add_column("Details", style="white")

    env_table.add_row("Host OS & Controller", f"{host.os_name} | {'USB 3.x xHCI Detected' if host.has_usb3_controller else 'USB 2.0 EHCI'}")
    
    dev_status = f"{device.manufacturer} {device.model} ({device.device_codename}) [Serial: {device.serial}]"
    if device.is_usb2_limited:
        dev_status += f"\n[bold red]⚠ Phone Hardware Limit: USB 2.0 PHY only ({device.limitation_reason})[/bold red]"
    env_table.add_row("Android Device", dev_status)
    
    phy_style = "bold green" if link.is_superspeed else "bold yellow"
    env_table.add_row("Negotiated PHY Link", f"[{phy_style}]{link.description} (Source: {link.source})[/{phy_style}]")

    if power:
        pwr_text = f"{power.voltage_v:.2f} V  |  {abs(power.current_now_ma):.0f} mA  |  [bold]{power.power_watts:.2f} W[/bold]  ({power.charging_status} via {power.charge_source}, Temp: {power.temperature_c:.1f}°C)"
        env_table.add_row("Power Delivery", pwr_text)

    console.print(env_table)
    console.print()

    # Throughput Iterations Table
    tp_table = Table(title=f"RAM-to-RAM Throughput ({throughput.total_size_mb} MB synthetic payload)", box=box.ROUNDED, expand=True)
    tp_table.add_column("Iteration", justify="center", style="cyan")
    tp_table.add_column("Transferred", justify="right")
    tp_table.add_column("Time (s)", justify="right")
    tp_table.add_column("Throughput (MB/s)", justify="right", style="bold green")
    tp_table.add_column("Throughput (Gbps)", justify="right", style="bold blue")
    tp_table.add_column("Status", justify="center")

    for run in throughput.runs:
        status_text = "[bold green]PASS[/bold green]" if run.success else f"[bold red]FAIL: {run.error}[/bold red]"
        tp_table.add_row(
            f"Run #{run.iteration}",
            f"{run.bytes_transferred / (1024 * 1024):.1f} MB",
            f"{run.duration_seconds:.2f} s",
            f"{run.speed_mb_s:.2f} MB/s" if run.success else "0.00",
            f"{run.speed_gbps:.3f} Gbps" if run.success else "0.000",
            status_text,
        )

    console.print(tp_table)
    console.print()

    # Throughput Summary Table
    stats_table = Table(title="Throughput Aggregation Statistics", box=box.ROUNDED, expand=True)
    stats_table.add_column("Metric", style="bold yellow")
    stats_table.add_column("Value", style="bold white")

    stats_table.add_row("Mean Speed", f"[bold green]{throughput.mean_speed_mb_s:.2f} MB/s[/bold green] ({throughput.mean_speed_gbps:.3f} Gbps / {throughput.mean_speed_mbps:.1f} Mbps)")
    stats_table.add_row("Median Speed", f"{throughput.median_speed_mb_s:.2f} MB/s")
    stats_table.add_row("Min / Max Speed", f"{throughput.min_speed_mb_s:.2f} MB/s  /  {throughput.max_speed_mb_s:.2f} MB/s")
    stats_table.add_row("Standard Deviation", f"± {throughput.stdev_speed_mb_s:.2f} MB/s")
    stats_table.add_row("Overall Benchmark Duration", f"{throughput.overall_duration_seconds:.2f} seconds")

    console.print(stats_table)
    console.print()

    # Verdict Badge
    badge_style = {
        CableGrade.USB_3_1_GEN_2_SUPERSPEED_PLUS: "bold white on green",
        CableGrade.USB_3_1_GEN_1_SUPERSPEED: "bold white on dark_green",
        CableGrade.USB_2_0_HIGH_SPEED: "bold white on blue",
        CableGrade.DEGRADED_OR_PACKET_LOSS: "bold white on red",
        CableGrade.CHARGE_ONLY: "bold white on dark_red",
        CableGrade.UNKNOWN: "bold white on grey50",
    }.get(result.grade, "bold white on blue")

    verdict_panel = Panel(
        Align.center(
            f"[{badge_style}]  FINAL CABLE RATING: {result.rating_display}  [/{badge_style}]\n\n"
            f"[bold]Quality Score:[/bold] {result.quality_score}/100  |  [bold]Confidence:[/bold] {result.confidence_percent}%\n"
            f"{result.summary_message}"
        ),
        title="Diagnostic Classification",
        border_style="bright_blue",
        box=box.DOUBLE,
    )
    console.print(verdict_panel)

    # Bottlenecks & Recommendations
    if result.bottleneck_description:
        console.print(Panel(f"[bold red]Bottleneck Detected:[/bold red] {result.bottleneck_description}", border_style="red", box=box.ROUNDED))

    if result.recommendations:
        rec_list = "\n".join(f"• {rec}" for rec in result.recommendations)
        console.print(Panel(rec_list, title="Recommendations", border_style="green", box=box.ROUNDED))
    console.print()


@app.command()
def benchmark(
    size_mb: int = typer.Option(1024, "--size-mb", "-m", help="Payload size per iteration in Megabytes (streamed to RAM)"),
    iterations: int = typer.Option(3, "--iterations", "-i", help="Number of benchmark iterations to execute"),
    json_output: bool = typer.Option(False, "--json-output", "-j", help="Output results in machine-readable JSON format"),
    device_serial: Optional[str] = typer.Option(None, "--device", "-s", help="Target specific Android device serial"),
    include_power: bool = typer.Option(True, "--include-power/--skip-power", help="Query battery voltage, amperage, and power"),
    chunk_size_kb: int = typer.Option(1024, "--chunk-size-kb", help="Streaming chunk size in Kilobytes (default: 1024 KB)"),
    dry_run: bool = typer.Option(False, "--dry-run", "--mock", help="Simulate benchmark with synthetic data (offline testing)"),
) -> None:
    """Run USB cable benchmark and diagnostics using ADB."""
    if dry_run:
        device, link, host, throughput, power = create_mock_data(size_mb, iterations)
    else:
        adb = ADBController(serial=device_serial)
        
        # Check ADB installation
        if not adb.check_adb_installed():
            if json_output:
                print(json.dumps({"error": "ADB is not installed or not in PATH."}))
            else:
                console.print("[bold red]Error: ADB is not installed or not found in system PATH.[/bold red]")
            sys.exit(1)

        # Inspect connected device
        try:
            device = adb.inspect_device()
        except Exception as e:
            if json_output:
                print(json.dumps({"error": str(e)}))
            else:
                console.print(f"[bold red]Device Error: {e}[/bold red]")
            sys.exit(1)

        # Link checker
        link_checker = LinkChecker(adb)
        link = link_checker.check_android_link()
        host = link_checker.check_host_usb()

        # Power monitor
        power: Optional[BatteryInfo] = None
        if include_power:
            power_monitor = PowerMonitor(adb)
            power = power_monitor.get_battery_info()

        # Run Throughput Benchmark with Rich progress bar if interactive
        throughput_bench = ThroughputBenchmark(adb, chunk_size_bytes=chunk_size_kb * 1024)

        if not json_output:
            console.print(f"[cyan]Streaming {size_mb} MB across {iterations} iterations into Android /dev/null...[/cyan]")
            with Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                overall_task = progress.add_task("[green]Overall Progress", total=iterations)
                current_iter_task = progress.add_task("[yellow]Current Run", total=size_mb * 1024 * 1024)

                def run_start(iter_idx: int, total_iters: int):
                    progress.reset(current_iter_task)
                    progress.update(current_iter_task, description=f"[yellow]Run #{iter_idx}/{total_iters}")

                def progress_update(bytes_written: int, total_bytes: int, speed: float):
                    progress.update(current_iter_task, completed=bytes_written)

                def run_finish(res: SingleRunResult):
                    progress.advance(overall_task, 1)

                throughput = throughput_bench.benchmark(
                    size_mb=size_mb,
                    iterations=iterations,
                    run_start_cb=run_start,
                    progress_cb=progress_update,
                    run_finish_cb=run_finish,
                )
        else:
            throughput = throughput_bench.benchmark(
                size_mb=size_mb,
                iterations=iterations,
            )

    # Classify Cable
    classification = CableClassifier.classify(
        device=device,
        link=link,
        host=host,
        throughput=throughput,
        power=power,
    )

    # Output results
    if json_output:
        data = {
            "device": {
                "serial": device.serial,
                "model": device.model,
                "manufacturer": device.manufacturer,
                "is_usb2_limited": device.is_usb2_limited,
                "limitation_reason": device.limitation_reason,
            },
            "link": {
                "raw_speed": link.raw_speed,
                "speed_mbps": link.speed_mbps,
                "description": link.description,
                "source": link.source,
                "is_superspeed": link.is_superspeed,
            },
            "host": {
                "os_name": host.os_name,
                "has_usb3_controller": host.has_usb3_controller,
                "host_controllers": host.host_controllers,
            },
            "power": {
                "voltage_v": power.voltage_v if power else 0.0,
                "current_now_ma": power.current_now_ma if power else 0.0,
                "power_watts": power.power_watts if power else 0.0,
                "charging_status": power.charging_status if power else "Unknown",
                "charge_source": power.charge_source if power else "Unknown",
                "level_percent": power.level_percent if power else 0,
                "temperature_c": power.temperature_c if power else 0.0,
            } if power else None,
            "throughput": {
                "total_size_mb": throughput.total_size_mb,
                "iterations": throughput.iterations,
                "mean_speed_mb_s": round(throughput.mean_speed_mb_s, 2),
                "mean_speed_gbps": round(throughput.mean_speed_gbps, 3),
                "mean_speed_mbps": round(throughput.mean_speed_mbps, 1),
                "median_speed_mb_s": round(throughput.median_speed_mb_s, 2),
                "min_speed_mb_s": round(throughput.min_speed_mb_s, 2),
                "max_speed_mb_s": round(throughput.max_speed_mb_s, 2),
                "stdev_speed_mb_s": round(throughput.stdev_speed_mb_s, 2),
                "overall_duration_seconds": round(throughput.overall_duration_seconds, 2),
                "all_successful": throughput.all_successful,
                "runs": [
                    {
                        "iteration": r.iteration,
                        "bytes_transferred": r.bytes_transferred,
                        "duration_seconds": round(r.duration_seconds, 3),
                        "speed_mb_s": round(r.speed_mb_s, 2),
                        "speed_gbps": round(r.speed_gbps, 3),
                        "success": r.success,
                        "error": r.error,
                    }
                    for r in throughput.runs
                ],
            },
            "classification": {
                "grade": classification.grade.value,
                "rating_display": classification.rating_display,
                "quality_score": classification.quality_score,
                "confidence_percent": classification.confidence_percent,
                "is_bottlenecked_by_device": classification.is_bottlenecked_by_device,
                "is_bottlenecked_by_host": classification.is_bottlenecked_by_host,
                "bottleneck_description": classification.bottleneck_description,
                "summary_message": classification.summary_message,
                "detailed_findings": classification.detailed_findings,
                "recommendations": classification.recommendations,
            },
        }
        print(json.dumps(data, indent=2))
    else:
        print_rich_report(
            device=device,
            link=link,
            host=host,
            throughput=throughput,
            power=power,
            result=classification,
        )


if __name__ == "__main__":
    app()
