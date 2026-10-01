"""Live system metrics sampler.

Reads /proc counters and turns them into rates/percentages on each sample,
keeping short rolling histories for the sparklines. All system-wide files
(/proc/stat, /proc/meminfo, /proc/net/dev, /proc/diskstats, /proc/loadavg)
reflect the host kernel even inside a Flatpak sandbox, so this works there
too (the app shares the host network namespace).
"""

import os
import re
import time
from collections import deque

HISTORY = 60  # samples kept (~1 minute at a 1s cadence)

# Whole block devices only (exclude partitions, loop/ram/device-mapper).
_DISK_RE = re.compile(r"(sd[a-z]+|vd[a-z]+|hd[a-z]+|nvme\d+n\d+|mmcblk\d+)$")


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


class Sampler:
    def __init__(self, history=HISTORY):
        self.history = history
        self.ncpu = os.cpu_count() or 1

        z = [0.0] * history
        self.cpu_hist = deque(z, maxlen=history)
        self.mem_hist = deque(z, maxlen=history)
        self.net_rx_hist = deque(z, maxlen=history)
        self.net_tx_hist = deque(z, maxlen=history)
        self.disk_rd_hist = deque(z, maxlen=history)
        self.disk_wr_hist = deque(z, maxlen=history)
        self.load_hist = deque(z, maxlen=history)
        self.percore = [0.0] * self.ncpu

        self._prev_cpu = self._read_cpu()
        self._prev_percpu = self._read_percpu()
        self._prev_net = self._read_net()
        self._prev_disk = self._read_disk()
        self._prev_t = time.monotonic()

    # ---- raw readers -----------------------------------------------------
    def _read_cpu(self):
        for line in _read("/proc/stat").splitlines():
            if line.startswith("cpu "):
                p = [int(x) for x in line.split()[1:]]
                idle = p[3] + (p[4] if len(p) > 4 else 0)  # idle + iowait
                return sum(p), idle
        return 0, 0

    def _read_percpu(self):
        out = []
        for line in _read("/proc/stat").splitlines():
            if line.startswith("cpu") and not line.startswith("cpu "):
                p = [int(x) for x in line.split()[1:]]
                idle = p[3] + (p[4] if len(p) > 4 else 0)
                out.append((sum(p), idle))
        return out

    def _read_net(self):
        rx = tx = 0
        for line in _read("/proc/net/dev").splitlines():
            if ":" not in line:
                continue
            iface, data = line.split(":", 1)
            if iface.strip() == "lo":
                continue
            f = data.split()
            if len(f) >= 9:
                rx += int(f[0])
                tx += int(f[8])
        return rx, tx

    def _read_disk(self):
        rd = wr = 0
        for line in _read("/proc/diskstats").splitlines():
            f = line.split()
            if len(f) < 10:
                continue
            if not _DISK_RE.fullmatch(f[2]):
                continue
            rd += int(f[5])  # sectors read
            wr += int(f[9])  # sectors written
        return rd, wr

    def _mem(self):
        info = {}
        for line in _read("/proc/meminfo").splitlines():
            key, _, rest = line.partition(":")
            m = re.search(r"(\d+)", rest)
            if m:
                info[key.strip()] = int(m.group(1))  # kB
        total = info.get("MemTotal", 0)
        avail = info.get("MemAvailable", info.get("MemFree", 0))
        used = max(total - avail, 0)
        swap_total = info.get("SwapTotal", 0)
        swap_free = info.get("SwapFree", 0)
        swap_used = max(swap_total - swap_free, 0)
        pct = (used / total * 100.0) if total else 0.0
        gib = 1024 * 1024
        return {
            "pct": pct,
            "used_gib": used / gib,
            "total_gib": total / gib,
            "swap_pct": (swap_used / swap_total * 100.0) if swap_total else 0.0,
            "swap_used_gib": swap_used / gib,
            "swap_total_gib": swap_total / gib,
        }

    def _loadavg(self):
        f = _read("/proc/loadavg").split()
        try:
            return float(f[0]), float(f[1]), float(f[2])
        except (IndexError, ValueError):
            return 0.0, 0.0, 0.0

    # ---- one sample ------------------------------------------------------
    def sample(self):
        now = time.monotonic()
        dt = max(now - self._prev_t, 1e-3)

        tot, idle = self._read_cpu()
        d_tot = tot - self._prev_cpu[0]
        d_idle = idle - self._prev_cpu[1]
        cpu = 100.0 * (1 - d_idle / d_tot) if d_tot > 0 else 0.0
        cpu = min(max(cpu, 0.0), 100.0)
        self._prev_cpu = (tot, idle)
        self.cpu_hist.append(cpu)

        pc = self._read_percpu()
        self.percore = []
        for (t, i), (pt, pi) in zip(pc, self._prev_percpu):
            d = t - pt
            di = i - pi
            self.percore.append(min(max(100.0 * (1 - di / d) if d > 0 else 0.0, 0.0), 100.0))
        self._prev_percpu = pc

        mem = self._mem()
        self.mem_hist.append(mem["pct"])

        rx, tx = self._read_net()
        rx_rate = max(rx - self._prev_net[0], 0) / dt
        tx_rate = max(tx - self._prev_net[1], 0) / dt
        self._prev_net = (rx, tx)
        self.net_rx_hist.append(rx_rate)
        self.net_tx_hist.append(tx_rate)

        rd, wr = self._read_disk()
        rd_rate = max(rd - self._prev_disk[0], 0) * 512 / dt
        wr_rate = max(wr - self._prev_disk[1], 0) * 512 / dt
        self._prev_disk = (rd, wr)
        self.disk_rd_hist.append(rd_rate)
        self.disk_wr_hist.append(wr_rate)

        load = self._loadavg()
        self.load_hist.append(load[0])

        self._prev_t = now
        return {
            "cpu": cpu,
            "mem": mem,
            "net_rx": rx_rate,
            "net_tx": tx_rate,
            "disk_rd": rd_rate,
            "disk_wr": wr_rate,
            "load": load,
        }


def human_rate(bytes_per_s):
    """Format a byte/s rate compactly (B/s, KB/s, MB/s, GB/s)."""
    v = float(bytes_per_s)
    for unit in ("B", "KB", "MB", "GB"):
        if v < 1024 or unit == "GB":
            return f"{v:.0f} {unit}/s" if unit == "B" else f"{v:.1f} {unit}/s"
        v /= 1024
    return f"{v:.1f} GB/s"
