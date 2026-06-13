"""Detect RAM pressure and recommend safe dialer settings for this PC."""
from __future__ import annotations


def system_ram_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        return 8.0


def chrome_process_count() -> int:
    try:
        import psutil
        count = 0
        for proc in psutil.process_iter(["name"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if name == "chrome.exe" or name == "chrome":
                    count += 1
            except Exception:
                continue
        return count
    except Exception:
        return 0


def recommended_slots(requested: int) -> int:
    """Cap concurrent Google Voice lines based on available RAM and Chrome load."""
    requested = max(1, int(requested or 1))
    ram = system_ram_gb()
    chrome = chrome_process_count()

    if ram < 10 or chrome >= 20:
        return min(requested, 1)
    if ram < 16 or chrome >= 10:
        return min(requested, 2)
    return min(requested, 3)


def recommended_amd_audio(requested: bool) -> bool:
    """Return whether local AMD audio should run on this PC."""
    if not requested:
        return False
    ram = system_ram_gb()
    chrome = chrome_process_count()
    if ram < 10 or chrome >= 25:
        return False
    return True


def effective_enable_ai_audio(cfg: dict) -> bool:
    """Apply system caps to enable_ai_audio from config."""
    requested = bool(cfg.get("enable_ai_audio", False))
    amd_mode = str(cfg.get("amd_mode", "heuristic") or "heuristic").lower()
    if amd_mode == "off":
        return False
    return recommended_amd_audio(requested)


def low_resource_reason(requested: int, effective: int) -> str:
    if effective >= requested:
        return ""
    ram = system_ram_gb()
    chrome = chrome_process_count()
    parts = [f"Using {effective} line(s) instead of {requested}"]
    if ram < 10:
        parts.append(f"RAM is ~{ram:.0f} GB (8 GB PCs should use 1 line)")
    if chrome >= 10:
        parts.append(f"{chrome} Chrome processes are open")
    parts.append("Close extra Chrome windows to run more lines")
    return " — ".join(parts)
