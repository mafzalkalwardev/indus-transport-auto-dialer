"""Tests for unified transcript classifier."""
from src.detection.unified_transcript_classifier import classify_transcript
from src.detection.transcript_evidence import TranscriptEvidenceScorer


def test_human_greeting():
    result = classify_transcript("Hello?")
    assert result.classification == "human"
    assert result.human_score >= 0.65


def test_voicemail_phrase():
    result = classify_transcript("Please leave your message after the tone.")
    assert result.classification == "voicemail"
    assert result.voicemail_score >= 0.8


def test_call_screening():
    result = classify_transcript("Please state your name after the tone.")
    assert result.classification == "call_screening_prompt"


def test_transcript_scorer_weights():
    scored = TranscriptEvidenceScorer().score("Hi, yes speaking")
    assert scored.human_score >= 0.65
