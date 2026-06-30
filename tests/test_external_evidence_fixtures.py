import pytest

from src.detection.external_evidence_manager import ExternalEvidenceManager
from src.detection.external_evidence import (
    ExternalEvidence,
    ExternalLabel,
    ProviderHealth,
    ProviderName,
)
from src.detection.external_evidence_mapper import ExternalEvidenceMapper


@pytest.fixture
def manager():
    cfg = {
        "external_detector_enabled": True,
        "external_detector_mode": "prototype_b",
        "external_detector_merge_mode": "evidence_only",
        "external_detector_timeout_ms": 1500,
        "external_detector_fail_open": True,
        "external_detector_debug": False,
    }
    mgr = ExternalEvidenceManager(cfg)
    return mgr


def _fixture(label, transcript="", confidence=0.8):
    return {
        "classification": label,
        "transcript": transcript,
        "confidence": confidence,
        "latency_ms": 120,
        "reason": "fixture",
    }


def test_fixture_human_greeting(manager):
    manager.initialize()
    manager.load_fixture(_fixture("human", transcript="hello"))
    ev = manager.get_latest(call_id="call-1", line_id="0")
    assert ev is not None
    assert ev.is_human_like() is True
    assert ev.transcript == "hello"
    assert ev.provider_health == ProviderHealth.CONNECTED


def test_fixture_voicemail_greeting(manager):
    manager.initialize()
    manager.load_fixture(_fixture("voicemail", transcript="please leave a message after the tone", confidence=0.92))
    ev = manager.get_latest(call_id="call-1", line_id="0")
    assert ev is not None
    assert ev.is_voicemail_like() is True
    assert ev.confidence == pytest.approx(0.92)


def test_fixture_busy(manager):
    manager.initialize()
    manager.load_fixture(_fixture("busy", confidence=0.85))
    ev = manager.get_latest(call_id="call-1", line_id="0")
    assert ev is not None
    assert ev.is_busy_like() is True


def test_fixture_disconnected(manager):
    manager.initialize()
    manager.load_fixture(_fixture("disconnected_or_failed", confidence=0.74))
    ev = manager.get_latest(call_id="call-1", line_id="0")
    assert ev is not None
    assert ev.is_diagnostic_only() is True


def test_fixture_unknown(manager):
    manager.initialize()
    manager.load_fixture(_fixture("unknown", confidence=0.35))
    ev = manager.get_latest(call_id="call-1", line_id="0")
    assert ev is not None
    assert ev.is_diagnostic_only() is True


def test_fixture_advance_cycles(manager):
    manager.initialize()
    fixtures = [
        _fixture("unknown", confidence=0.3),
        _fixture("human", transcript="yes", confidence=0.7),
        _fixture("voicemail", transcript="leave a message", confidence=0.9),
    ]
    for f in fixtures:
        manager.load_fixture(f)
        ev = manager.get_latest()
        assert ev is not None
    manager.advance_fixture()
    ev = manager.get_latest()
    assert ev is not None
    assert ev.transcript == "yes"


def test_manager_disabled_returns_none():
    cfg = {
        "external_detector_enabled": False,
        "external_detector_mode": "prototype_a",
    }
    mgr = ExternalEvidenceManager(cfg)
    mgr.initialize()
    assert mgr.get_latest() is None
    assert mgr.get_health() == ProviderHealth.UNKNOWN


def test_manager_diagnostics():
    cfg = {
        "external_detector_enabled": True,
        "external_detector_mode": "prototype_b",
        "external_detector_merge_mode": "evidence_only",
        "external_detector_timeout_ms": 1500,
        "external_detector_fail_open": True,
        "external_detector_debug": True,
    }
    mgr = ExternalEvidenceManager(cfg)
    mgr.initialize()
    mgr.load_fixture(_fixture("human", transcript="hello", confidence=0.85))
    diag = mgr.get_diagnostics()
    assert diag["external_detector_enabled"] is True
    assert diag["external_detector_mode"] == "prototype_b"
    assert diag["external_last_label"] == ExternalLabel.HUMAN.value
    assert diag["external_confidence"] == pytest.approx(0.85)
    assert diag["external_provider_health"] == ProviderHealth.CONNECTED.value
    assert diag["external_transcript"] == "hello"


def test_fixture_conflict_human_then_voicemail(manager):
    manager.initialize()
    manager.load_fixture(_fixture("human", transcript="hello"))
    first = manager.get_latest()
    assert first.is_human_like() is True
    manager.advance_fixture()
    manager.load_fixture(_fixture("voicemail", transcript="please leave a message"))
    second = manager.get_latest()
    assert second.is_voicemail_like() is True
