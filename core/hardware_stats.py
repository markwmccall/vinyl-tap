import os
import subprocess

import psutil


def _fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"  # pragma: no cover


def _safe(fn):
    """Call fn(), returning None if any exception is raised."""
    try:
        return fn()
    except Exception:
        return None


def _read_os_release():
    with open("/etc/os-release") as f:
        pairs = {}
        for line in f:
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                pairs[k] = v.strip('"')
    return pairs.get("PRETTY_NAME")


def _read_uptime():
    import time
    uptime_secs = int(time.time() - psutil.boot_time())
    d, rem = divmod(uptime_secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    parts.append(f"{m}m")
    return " ".join(parts)


def _read_cpu_model():
    with open("/proc/cpuinfo") as f:
        for line in f:
            if line.startswith("Model"):
                return line.split(":", 1)[1].strip()
    return None


def _read_cpu_temp():
    with open("/sys/class/thermal/thermal_zone0/temp") as f:
        return round(int(f.read().strip()) / 1000, 1)


def _read_throttle():
    """Return (throttle_ok, flags) tuple from vcgencmd, or raise on failure."""
    result = subprocess.run(
        ["vcgencmd", "get_throttled"],
        capture_output=True, text=True, timeout=2,
    )
    hex_val = result.stdout.strip().split("=")[-1]
    throttled = int(hex_val, 16)
    flags = []
    if throttled & 0x1:     flags.append("Under-voltage detected")
    if throttled & 0x2:     flags.append("Arm frequency capped")
    if throttled & 0x4:     flags.append("Currently throttled")
    if throttled & 0x8:     flags.append("Soft temperature limit active")
    if throttled & 0x10000: flags.append("Under-voltage has occurred")
    if throttled & 0x20000: flags.append("Arm frequency has been capped")
    if throttled & 0x40000: flags.append("Throttling has occurred")
    if throttled & 0x80000: flags.append("Soft temperature limit has occurred")
    return throttled == 0, flags


def get_hardware_stats(nfc_connected: bool) -> dict:
    """Return a dict of hardware stats for the settings/hardware page.

    nfc_connected: pass nfc_service.get_nfc() is not None from the caller,
    to avoid a circular import.
    """
    mem = _safe(psutil.virtual_memory)
    swap = _safe(psutil.swap_memory)
    disk = _safe(lambda: psutil.disk_usage("/"))
    freq = _safe(psutil.cpu_freq)
    throttle = _safe(_read_throttle)
    return {
        "hostname":       _safe(lambda: os.uname().nodename),
        "os":             _safe(_read_os_release),
        "kernel":         _safe(lambda: os.uname().release),
        "uptime":         _safe(_read_uptime),
        "cpu_model":      _safe(_read_cpu_model),
        "cpu_cores":      _safe(lambda: psutil.cpu_count(logical=False) or psutil.cpu_count()),
        "cpu_percent":    _safe(lambda: psutil.cpu_percent(interval=0.1)),
        "cpu_freq_mhz":   round(freq.current) if freq else None,
        "cpu_temp_c":     _safe(_read_cpu_temp),
        "ram_used":       _fmt_bytes(mem.used) if mem else None,
        "ram_total":      _fmt_bytes(mem.total) if mem else None,
        "ram_percent":    mem.percent if mem else None,
        "swap_used":      _fmt_bytes(swap.used) if swap else None,
        "swap_total":     _fmt_bytes(swap.total) if swap else None,
        "disk_used":      _fmt_bytes(disk.used) if disk else None,
        "disk_free":      _fmt_bytes(disk.free) if disk else None,
        "disk_total":     _fmt_bytes(disk.total) if disk else None,
        "disk_percent":   disk.percent if disk else None,
        "nfc_connected":  nfc_connected,
        "throttle_ok":    throttle[0] if throttle else None,
        "throttle_flags": throttle[1] if throttle else None,
    }
