"""Clean up zombie QtWebEngine helpers left after a crash or force-close."""
from __future__ import annotations

import os
import subprocess
import sys

from src.dialer_logging import log_info, log_warning


def cleanup_stale_webengine_processes() -> int:
    """
    End orphan QtWebEngineProcess.exe instances on Windows.
    Safe when no other app on this machine uses Qt WebEngine.
    Returns number of processes terminated.
    """
    if sys.platform != "win32":
        return 0
    try:
        import psutil
    except ImportError:
        return _taskkill_webengine()

    current_pid = os.getpid()
    killed = 0
    for proc in psutil.process_iter(["pid", "name", "ppid"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if "qtwebengine" not in name:
                continue
            pid = int(proc.info["pid"])
            if pid == current_pid:
                continue
            ppid = proc.info.get("ppid")
            if ppid == current_pid:
                continue
            proc.kill()
            killed += 1
        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
            getattr(psutil, "ZombieProcess", psutil.NoSuchProcess),
            PermissionError,
            OSError,
        ):
            continue
    if killed:
        log_info(f"Cleaned up {killed} stale QtWebEngine process(es)")
    return killed


def _taskkill_webengine() -> int:
    try:
        result = subprocess.run(
            ["taskkill", "/F", "/IM", "QtWebEngineProcess.exe"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            log_info("Cleaned up QtWebEngineProcess via taskkill")
            return 1
    except Exception as exc:
        log_warning(f"Could not taskkill QtWebEngineProcess: {exc}")
    return 0
