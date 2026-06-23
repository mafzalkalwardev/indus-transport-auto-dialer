"""Safe label mapping from Chrome extension prototypes to Auto Dialer evidence."""
from __future__ import annotations

from typing import Any, Dict

from .external_evidence import (
    ExternalEvidence,
    ExternalLabel,
    ProviderHealth,
    ProviderName,
)


class ExternalEvidenceMapper:
    """Maps raw extension outputs to normalized ExternalEvidence.

    All mappings are evidence-only. No final state is ever emitted here.
    """

    @staticmethod
    def map_prototype_a(
        raw_label: str,
        confidence: float = 0.0,
        transcript: str = "",
        timestamp: float = 0.0,
        latency_ms: float = 0.0,
        provider_health: str = "unknown",
        diagnostic_reason: str = "",
        raw_payload: Dict[str, Any] | None = None,
    ) -> ExternalEvidence:
        label = raw_label.lower().replace(" ", "_") if raw_label else "unknown"
        if label not in {e.value for e in ExternalLabel}:
            label = ExternalLabel.UNKNOWN.value

        return ExternalEvidence(
            provider=ProviderName.PROTOTYPE_A,
            raw_label=label,
            confidence=float(confidence or 0.0),
            transcript=str(transcript or ""),
            timestamp=float(timestamp or 0.0),
            latency_ms=float(latency_ms or 0.0),
            provider_health=ProviderHealth(provider_health.lower())
            if provider_health
            else ProviderHealth.UNKNOWN,
            diagnostic_reason=str(diagnostic_reason or ""),
            raw_payload=raw_payload or {},
        )

    @staticmethod
    def map_prototype_b(
        raw_label: str,
        confidence: float = 0.0,
        transcript: str = "",
        timestamp: float = 0.0,
        latency_ms: float = 0.0,
        provider_health: str = "unknown",
        diagnostic_reason: str = "",
        raw_payload: Dict[str, Any] | None = None,
    ) -> ExternalEvidence:
        label = raw_label.lower().replace(" ", "_") if raw_label else "unknown"
        if label not in {e.value for e in ExternalLabel}:
            label = ExternalLabel.UNKNOWN.value

        return ExternalEvidence(
            provider=ProviderName.PROTOTYPE_B,
            raw_label=label,
            confidence=float(confidence or 0.0),
            transcript=str(transcript or ""),
            timestamp=float(timestamp or 0.0),
            latency_ms=float(latency_ms or 0.0),
            provider_health=ProviderHealth(provider_health.lower())
            if provider_health
            else ProviderHealth.UNKNOWN,
            diagnostic_reason=str(diagnostic_reason or ""),
            raw_payload=raw_payload or {},
        )

    @staticmethod
    def merge_into_audio_features(audio_features: Any, evidence: ExternalEvidence) -> Any:
        """Safely merge external evidence into existing audio features.

        This only boosts signals; it never removes existing local evidence.
        It also never triggers answer-clock start — that remains DOM-only.
        """
        if evidence is None or not evidence.is_valid():
            return audio_features

        if audio_features is None:
            from src.detection.audio_evidence import AudioEvidence
            audio_features = AudioEvidence()

        transcript = str(getattr(audio_features, "transcript", "") or "")
        external_transcript = evidence.transcript.strip()

        if evidence.is_human_like():
            setattr(audio_features, "human_greeting_detected", True)
            setattr(audio_features, "has_speech_like", True)
            if external_transcript and external_transcript not in transcript:
                transcript = f"{transcript} {external_transcript}".strip()

        if evidence.is_voicemail_like():
            setattr(audio_features, "voicemail_keywords_detected_count",
                    int(getattr(audio_features, "voicemail_keywords_detected_count", 0) or 0) + 1)
            if external_transcript and external_transcript not in transcript:
                transcript = f"{transcript} {external_transcript}".strip()

        if evidence.is_busy_like():
            existing = float(getattr(audio_features, "busy_tone_cadence_confidence", 0.0) or 0.0)
            setattr(audio_features, "busy_tone_cadence_confidence", max(existing, 0.9))

        if evidence.is_ivr_like():
            if external_transcript and external_transcript not in transcript:
                transcript = f"{transcript} {external_transcript}".strip()

        if transcript:
            setattr(audio_features, "transcript", transcript)

        return audio_features

    @staticmethod
    def evidence_to_debug(evidence: ExternalEvidence | None) -> Dict[str, Any]:
        if evidence is None:
            return {}
        return {
            "external_provider": evidence.provider.value,
            "external_label": evidence.raw_label,
            "external_confidence": round(evidence.confidence, 3),
            "external_transcript": evidence.transcript[:200],
            "external_health": evidence.provider_health.value,
            "external_latency_ms": evidence.latency_ms,
            "external_diagnostic_reason": evidence.diagnostic_reason,
            "external_pre_answer": evidence.pre_answer,
            "external_post_answer": evidence.post_answer,
            "external_accepted": evidence.is_valid(),
        }
