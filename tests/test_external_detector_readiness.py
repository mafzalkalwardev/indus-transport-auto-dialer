"""Tests for external detector readiness: dry-run and health check."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from scripts.live_call_smoke_dry_run import simulate_call, main as dry_run_main
from scripts.external_detector_health import load_config, check_http, main as health_main


def test_simulate_call_returns_expected_keys():
    rec = simulate_call("+15551234567")
    assert rec["phone"] == "+15551234567"
    assert rec["final"] in {"NO_ANSWER", "VOICEMAIL", "CONNECTED"}
    assert len(rec["states"]) >= 2
    assert rec["states"][0]["state"] == "DIALING"
    assert rec["states"][1]["state"] == "RINGING"
    assert rec["external_detector_enabled"] is False
    assert rec["detector_confidence"] == 1.0


def test_dry_run_writes_report():
    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = os.path.join(tmpdir, "dry_run_report.json")
        sys.argv = [
            "scripts/live_call_smoke_dry_run.py",
            "+15551234567",
            "--dry-run",
            "--report-path",
            report_path,
        ]
        rc = dry_run_main()
        assert rc == 0
        assert os.path.exists(report_path)
        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["mode"] == "dry-run"
        assert len(data["results"]) == 1
        assert data["results"][0]["final"] in {"NO_ANSWER", "VOICEMAIL", "CONNECTED"}


def test_dry_run_does_not_dial(monkeypatch):
    calls = []

    def fake_dial(*args, **kwargs):
        calls.append((args, kwargs))
        return None

    monkeypatch.setattr("scripts.live_call_smoke_dry_run.simulate_call", lambda phone: {
        "phone": phone,
        "final": "NO_ANSWER",
        "states": [],
        "external_detector_enabled": False,
        "detector_reason": "sim",
        "detector_confidence": 1.0,
    })

    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = os.path.join(tmpdir, "report.json")
        sys.argv = [
            "scripts/live_call_smoke_dry_run.py",
            "+15551234567",
            "--dry-run",
            "--report-path",
            report_path,
        ]
        rc = dry_run_main()
        assert rc == 0
        assert calls == []


def test_health_check_disabled():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as cfg:
        json.dump({"external_detector_enabled": False}, cfg)
        cfg_path = cfg.name
    try:
        sys.argv = ["scripts/external_detector_health.py"]
        # monkeypatch load_config path
        import scripts.external_detector_health as health_mod
        original_load = health_mod.load_config

        def fake_load():
            return {"external_detector_enabled": False}

        health_mod.load_config = fake_load
        try:
            rc = health_main()
        finally:
            health_mod.load_config = original_load
        assert rc == 0
    finally:
        os.unlink(cfg_path)


def test_health_check_offline_backend_fail_closed(monkeypatch):
    import scripts.external_detector_health as health_mod
    original_load = health_mod.load_config

    def fake_load():
        return {
            "external_detector_enabled": True,
            "external_detector_mode": "prototype_a",
            "external_detector_timeout_ms": 500,
            "external_detector_fail_open": False,
        }

    monkeypatch.setattr(
        health_mod,
        "check_http",
        lambda url, timeout=2.0: {"url": url, "status": "FAIL", "code": None, "latency_ms": None},
    )
    health_mod.load_config = fake_load
    try:
        sys.argv = ["scripts/external_detector_health.py"]
        rc = health_main()
    finally:
        health_mod.load_config = original_load
    assert rc == 1


def test_health_check_offline_backend_fail_open(monkeypatch):
    import scripts.external_detector_health as health_mod
    original_load = health_mod.load_config

    def fake_load():
        return {
            "external_detector_enabled": True,
            "external_detector_mode": "prototype_a",
            "external_detector_timeout_ms": 500,
            "external_detector_fail_open": True,
        }

    monkeypatch.setattr(
        health_mod,
        "check_http",
        lambda url, timeout=2.0: {"url": url, "status": "FAIL", "code": None, "latency_ms": None},
    )
    health_mod.load_config = fake_load
    try:
        sys.argv = ["scripts/external_detector_health.py"]
        rc = health_main()
    finally:
        health_mod.load_config = original_load
    assert rc == 0


def test_config_default_disabled():
    cfg = load_config()
    assert cfg.get("external_detector_enabled", False) is False