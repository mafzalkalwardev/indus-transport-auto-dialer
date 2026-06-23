import pytest

from src.detection.external_evidence import (
    ExternalEvidence,
    ExternalLabel,
    ProviderHealth,
    ProviderName,
)
from src.detection.external_evidence_mapper import ExternalEvidenceMapper


def test_external_evidence_is_valid_when_connected_and_positive_confidence():
    ev = ExternalEvidence(
        provider=ProviderName.PROTOTYPE_A,
        raw_label=ExternalLabel.HUMAN_PICKED.value,
        confidence=0.8,
        provider_health=ProviderHealth.CONNECTED,
    )
    assert ev.is_valid() is True


def test_external_evidence_is_invalid_when_disconnected():
    ev = ExternalEvidence(
        provider=ProviderName.PROTOTYPE_A,
        raw_label=ExternalLabel.HUMAN_PICKED.value,
        confidence=0.8,
        provider_health=ProviderHealth.DISCONNECTED,
    )
    assert ev.is_valid() is False


def test_external_evidence_is_invalid_when_zero_confidence():
    ev = ExternalEvidence(
        provider=ProviderName.PROTOTYPE_A,
        raw_label=ExternalLabel.HUMAN_PICKED.value,
        confidence=0.0,
        provider_health=ProviderHealth.CONNECTED,
    )
    assert ev.is_valid() is False


@pytest.mark.parametrize("label", [
    ExternalLabel.HUMAN_PICKED.value,
    ExternalLabel.HUMAN.value,
])
def test_human_like_labels(label):
    ev = ExternalEvidence(
        provider=ProviderName.PROTOTYPE_A,
        raw_label=label,
        confidence=0.7,
    )
    assert ev.is_human_like() is True
    assert ev.is_voicemail_like() is False
    assert ev.is_busy_like() is False


@pytest.mark.parametrize("label", [
    ExternalLabel.VOICEMAIL_DETECTED.value,
    ExternalLabel.VOICEMAIL.value,
])
def test_voicemail_like_labels(label):
    ev = ExternalEvidence(
        provider=ProviderName.PROTOTYPE_A,
        raw_label=label,
        confidence=0.7,
    )
    assert ev.is_voicemail_like() is True
    assert ev.is_human_like() is False


@pytest.mark.parametrize("label", [
    ExternalLabel.BUSY_OR_FAILED.value,
    ExternalLabel.BUSY.value,
])
def test_busy_like_labels(label):
    ev = ExternalEvidence(
        provider=ProviderName.PROTOTYPE_A,
        raw_label=label,
        confidence=0.7,
    )
    assert ev.is_busy_like() is True


def test_ringing_like_label():
    ev = ExternalEvidence(
        provider=ProviderName.PROTOTYPE_A,
        raw_label=ExternalLabel.STILL_RINGING.value,
        confidence=0.7,
    )
    assert ev.is_ringing_like() is True


def test_ivr_like_label():
    ev = ExternalEvidence(
        provider=ProviderName.PROTOTYPE_A,
        raw_label=ExternalLabel.CALL_SCREENING_PROMPT.value,
        confidence=0.7,
    )
    assert ev.is_ivr_like() is True


@pytest.mark.parametrize("label", [
    ExternalLabel.UNKNOWN.value,
    ExternalLabel.UNKNOWN_OR_SILENCE.value,
    ExternalLabel.NO_ANSWER.value,
    ExternalLabel.ENDED.value,
    ExternalLabel.DISCONNECTED_OR_FAILED.value,
])
def test_diagnostic_only_labels(label):
    ev = ExternalEvidence(
        provider=ProviderName.PROTOTYPE_B,
        raw_label=label,
        confidence=0.5,
    )
    assert ev.is_diagnostic_only() is True


def test_map_prototype_a_unknown():
    ev = ExternalEvidenceMapper.map_prototype_a("unknown", confidence=0.4)
    assert ev.provider == ProviderName.PROTOTYPE_A
    assert ev.raw_label == ExternalLabel.UNKNOWN.value
    assert ev.confidence == 0.4


def test_map_prototype_a_human_picked():
    ev = ExternalEvidenceMapper.map_prototype_a(
        "human_picked",
        confidence=0.85,
        transcript="hello",
    )
    assert ev.is_human_like() is True
    assert ev.transcript == "hello"


def test_map_prototype_a_voicemail_detected():
    ev = ExternalEvidenceMapper.map_prototype_a(
        "voicemail_detected",
        confidence=0.9,
        transcript="please leave a message",
    )
    assert ev.is_voicemail_like() is True
    assert ev.transcript == "please leave a message"


def test_map_prototype_a_call_screening_prompt():
    ev = ExternalEvidenceMapper.map_prototype_a(
        "call_screening_prompt",
        confidence=0.9,
    )
    assert ev.is_ivr_like() is True


def test_map_prototype_a_busy_or_failed():
    ev = ExternalEvidenceMapper.map_prototype_a(
        "busy_or_failed",
        confidence=0.8,
    )
    assert ev.is_busy_like() is True


def test_map_prototype_b_human():
    ev = ExternalEvidenceMapper.map_prototype_b("human", confidence=0.78)
    assert ev.provider == ProviderName.PROTOTYPE_B
    assert ev.is_human_like() is True


def test_map_prototype_b_voicemail():
    ev = ExternalEvidenceMapper.map_prototype_b(
        "voicemail",
        confidence=0.92,
        transcript="leave a message",
    )
    assert ev.is_voicemail_like() is True


def test_map_prototype_b_busy():
    ev = ExternalEvidenceMapper.map_prototype_b("busy", confidence=0.85)
    assert ev.is_busy_like() is True


def test_map_prototype_b_disconnected():
    ev = ExternalEvidenceMapper.map_prototype_b(
        "disconnected_or_failed",
        confidence=0.74,
    )
    assert ev.is_diagnostic_only() is True


def test_map_prototype_b_unknown_or_silence():
    ev = ExternalEvidenceMapper.map_prototype_b("unknown_or_silence", confidence=0.7)
    assert ev.is_diagnostic_only() is True


def test_map_prototype_b_unknown():
    ev = ExternalEvidenceMapper.map_prototype_b("unknown", confidence=0.35)
    assert ev.is_diagnostic_only() is True


def test_mapper_normalizes_case_and_spaces():
    ev = ExternalEvidenceMapper.map_prototype_a("Human Picked", confidence=0.5)
    assert ev.raw_label == ExternalLabel.HUMAN_PICKED.value
