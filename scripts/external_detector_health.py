"""Health check for external detectors (Prototype A or Prototype B)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.paths import LOGS_DIR

PROTOTYPE_A_URL = "http://127.0.0.1:8787/health"
PROTOTYPE_B_URL = "http://localhost:3100/health"


def load_config() -> dict:
    config_path = os.path.join(ROOT, "dialer_config.json")
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def check_http(url: str, timeout: float = 2.0) -> dict:
    result = {"url": url, "status": "FAIL", "code": None, "latency_ms": None}
    try:
        req = urllib.request.Request(url, method="GET")
        start = datetime.now()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result["code"] = getattr(resp, "status", None)
            result["latency_ms"] = int((datetime.now() - start).total_seconds() * 1000)
        if result["code"] and 200 <= result["code"] < 300:
            result["status"] = "PASS"
    except urllib.error.URLError as exc:
        result["reason"] = str(exc)
    except Exception as exc:
        result["reason"] = repr(exc)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Check external detector health")
    parser.add_argument("--mode", choices=["prototype_a", "prototype_b"], help="Force detector mode")
    args = parser.parse_args()

    cfg = load_config()
    enabled = bool(cfg.get("external_detector_enabled", False))
    mode = args.mode or cfg.get("external_detector_mode", "prototype_a")
    timeout = float(cfg.get("external_detector_timeout_ms", 2000)) / 1000.0

    print(f"Config: enabled={enabled}, mode={mode}, timeout={timeout:.2f}s", flush=True)

    if not enabled:
        print("External detector: DISABLED (default safe state)", flush=True)
        print("Result: PASS", flush=True)
        return 0

    url = PROTOTYPE_A_URL if mode == "prototype_a" else PROTOTYPE_B_URL
    probe = check_http(url, timeout=timeout)
    print(f"Probe {url}: {probe['status']} code={probe['code']} latency={probe['latency_ms']}ms", flush=True)

    if probe["status"] == "PASS":
        print("External detector: UP", flush=True)
        print("Result: PASS", flush=True)
        return 0

    fail_open = bool(cfg.get("external_detector_fail_open", True))
    print(f"External detector: DOWN (fail_open={fail_open})", flush=True)
    if fail_open:
        print("Result: WARN — backend down; continuing with DOM-only detection", flush=True)
        return 0
    print("Result: FAIL", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())