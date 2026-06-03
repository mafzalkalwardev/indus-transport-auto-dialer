#!/usr/bin/env python3
"""Log WebEngine and system memory every 5 minutes during a soak test."""
from __future__ import annotations

import csv
import os
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.paths import LOGS_DIR
from src.slot_watchdog import webengine_total_memory_mb

INTERVAL_SEC = 300
OUT = os.path.join(LOGS_DIR, "load_test_metrics.csv")


def main() -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)
    new_file = not os.path.isfile(OUT)
    print(f"Logging every {INTERVAL_SEC}s to {OUT}")
    print("Stop with Ctrl+C")

    try:
        import psutil
    except ImportError:
        print("Install psutil: pip install psutil")
        sys.exit(1)

    with open(OUT, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow([
                "timestamp",
                "webengine_mb",
                "system_ram_percent",
                "system_ram_used_mb",
            ])
        while True:
            vm = psutil.virtual_memory()
            w.writerow([
                datetime.now().isoformat(timespec="seconds"),
                webengine_total_memory_mb(),
                round(vm.percent, 1),
                int(vm.used / (1024 * 1024)),
            ])
            f.flush()
            print(
                datetime.now().strftime("%H:%M:%S"),
                f"WebEngine={webengine_total_memory_mb()} MB",
                f"RAM={vm.percent:.1f}%",
            )
            time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
