"""Linux host measurements for the chat load test."""

import csv
from datetime import datetime, timezone
import os
from pathlib import Path
from threading import Event, Thread


def snapshot():
    cpu = Path("/proc/stat").read_text().splitlines()
    ticks = [int(value) for value in cpu[0].split()[1:9]]
    memory = dict(
        (key, int(value.split()[0]))
        for key, value in (line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    )
    counters = dict(line.split() for line in Path("/proc/vmstat").read_text().splitlines())
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "ticks": ticks,
        "ram_used_pct": round(100 * (1 - memory["MemAvailable"] / memory["MemTotal"]), 2),
        "ram_available_mib": round(memory["MemAvailable"] / 1024, 2),
        "swap_used_mib": round((memory["SwapTotal"] - memory["SwapFree"]) / 1024, 2),
        "swap_in": int(counters["pswpin"]),
        "swap_out": int(counters["pswpout"]),
        "oom_kill": int(counters["oom_kill"]) if "oom_kill" in counters else None,
    }


class VmMonitor:
    def __init__(self, initial):
        self.previous = initial
        self.samples = []
        self.stop = Event()
        self.thread = Thread(target=self.poll)
        self.error = None

    def capture(self):
        old, current = self.previous, snapshot()
        self.previous = current
        delta = [after - before for before, after in zip(old["ticks"], current["ticks"])]
        total = sum(delta)
        busy = total - delta[3] - delta[4] - delta[7]
        self.samples.append({
            "timestamp_utc": current["timestamp_utc"],
            "cpu_busy_pct": round(100 * busy / total, 2) if total else None,
            "io_wait_pct": round(100 * delta[4] / total, 2) if total else None,
            "cpu_steal_pct": round(100 * delta[7] / total, 2) if total else None,
            "ram_used_pct": current["ram_used_pct"],
            "ram_available_mib": current["ram_available_mib"],
            "swap_used_mib": current["swap_used_mib"],
            "swap_in_pages": current["swap_in"] - old["swap_in"],
            "swap_out_pages": current["swap_out"] - old["swap_out"],
            "oom_kills": current["oom_kill"] - old["oom_kill"] if current["oom_kill"] is not None else None,
        })

    def poll(self):
        try:
            while not self.stop.wait(1):
                self.capture()
            self.capture()
        except (OSError, ValueError, KeyError) as error:
            self.error = str(error)

    def write(self, path):
        if self.samples:
            with path.open("x", encoding="utf-8", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=list(self.samples[0]))
                writer.writeheader()
                writer.writerows(self.samples)

    def summary(self):
        lines = [f"Host: {os.uname().nodename} | logical CPUs: {os.cpu_count()}"]
        if not self.samples or self.error:
            lines.append(f"Host telemetry incomplete ({self.error or 'no chat traffic'}).")
        if not self.samples:
            return lines

        values = {}
        for key, aggregate, label, unit in (
            ("cpu_busy_pct", max, "Peak CPU busy", "%"),
            ("io_wait_pct", max, "Peak I/O wait", "%"),
            ("cpu_steal_pct", max, "Peak CPU steal", "%"),
            ("ram_available_mib", min, "Minimum available RAM", " MiB"),
            ("ram_used_pct", max, "Peak RAM used", "%"),
            ("swap_in_pages", sum, "Swap in", " pages"),
            ("swap_out_pages", sum, "Swap out", " pages"),
            ("oom_kills", sum, "OOM kills", ""),
        ):
            measured = [row[key] for row in self.samples if row[key] is not None]
            if measured:
                values[key] = aggregate(measured)
                lines.append(f"{label}: {values[key]}{unit}")
            else:
                lines.append(f"{label}: unavailable")
        signals = [
            label for key, limit, label in (
                ("cpu_busy_pct", 90, "CPU busy ≥ 90%"),
                ("ram_used_pct", 90, "RAM used ≥ 90%"),
                ("io_wait_pct", 10, "I/O wait ≥ 10%"),
                ("cpu_steal_pct", 5, "CPU steal ≥ 5%"),
                ("swap_out_pages", 1, "swap-out activity"),
                ("oom_kills", 1, "OOM kill"),
            ) if values.get(key, 0) >= limit
        ]
        lines.append("Host pressure signals: " + (", ".join(signals) or "none observed"))
        return lines
