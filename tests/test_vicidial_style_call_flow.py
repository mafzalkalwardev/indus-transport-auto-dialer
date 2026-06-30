from src.call_state_engine import CallStateEngine
from src.local_call_detector import DetectionConfig, DecisionState, LocalCallDetector


class DummyAudio:
    def __init__(
        self,
        *,
        rms=0.02,
        is_silent=False,
        has_speech_like=False,
        ringback_cadence_confidence=0.0,
        beep_hz_confidence=0.0,
        speech_duration_seconds=0.0,
        silence_duration_seconds=0.0,
        voicemail_keywords_detected_count=0,
        human_greeting_detected=False,
        short_speech_burst_detected=False,
        continuous_greeting_duration_seconds=0.0,
        beep_detected=False,
        busy_tone_cadence_confidence=0.0,
        background_noise_level=0.0,
        transcript="",
    ):
        self.rms = rms
        self.is_silent = is_silent
        self.has_speech_like = has_speech_like
        self.ringback_cadence_confidence = ringback_cadence_confidence
        self.beep_hz_confidence = beep_hz_confidence
        self.speech_duration_seconds = speech_duration_seconds
        self.silence_duration_seconds = silence_duration_seconds
        self.voicemail_keywords_detected_count = voicemail_keywords_detected_count
        self.human_greeting_detected = human_greeting_detected
        self.short_speech_burst_detected = short_speech_burst_detected
        self.continuous_greeting_duration_seconds = continuous_greeting_duration_seconds
        self.beep_detected = beep_detected
        self.busy_tone_cadence_confidence = busy_tone_cadence_confidence
        self.background_noise_level = background_noise_level
        self.transcript = transcript


def test_voicemail_phrase_while_ringing_stays_ringing():
    decision = CallStateEngine().classify(
        {
            "state": "VOICEMAIL",
            "callText": "calling please leave a message after the tone",
            "hasRingingText": True,
            "hasRingingNode": True,
            "hasTimer": False,
            "hasEnabledAnswerControl": False,
            "hasVoicemailCue": True,
        }
    )

    assert decision.state == "RINGING"


def test_answered_call_without_machine_signals_becomes_human_after_amd_window():
    det = LocalCallDetector(
        DetectionConfig(
            answered_pending_seconds=10,
            decision_stability_window=1,
        )
    )
    dom = {
        "state": "CONNECTED",
        "hasTimer": True,
        "hasEnabledAnswerControl": True,
        "hasVoicemailCue": False,
    }

    first = det.decide(
        dom_evidence=dom,
        audio_features=DummyAudio(),
        elapsed_seconds=5,
    )
    later = det.decide(
        dom_evidence=dom,
        audio_features=DummyAudio(
            has_speech_like=True,
            human_greeting_detected=True,
            short_speech_burst_detected=True,
            speech_duration_seconds=0.8,
            is_silent=False,
        ),
        elapsed_seconds=16,
    )

    assert first.state == DecisionState.ANSWERED_PENDING
    assert later.state == DecisionState.HUMAN


def test_human_pickup_is_not_terminal_and_can_end():
    det = LocalCallDetector(DetectionConfig(decision_stability_window=1))
    human = det.decide(
        dom_evidence={
            "state": "CONNECTED",
            "hasTimer": True,
            "hasEnabledAnswerControl": True,
        },
        audio_features=DummyAudio(
            has_speech_like=True,
            speech_duration_seconds=0.8,
            human_greeting_detected=True,
            short_speech_burst_detected=True,
        ),
        elapsed_seconds=5,
    )
    ended = det.decide(
        dom_evidence={"state": "ENDED"},
        audio_features=DummyAudio(),
        elapsed_seconds=20,
    )

    assert human.state == DecisionState.HUMAN
    assert ended.state == DecisionState.ENDED


def test_dom_voicemail_text_after_answer_can_confirm_machine():
    det = LocalCallDetector(
        DetectionConfig(
            voicemail_confirmation_count=1,
            voicemail_stability_cycles_required=1,
            decision_stability_window=1,
        )
    )
    dom = {
        "state": "VOICEMAIL",
        "callText": "please leave a message after the tone",
        "hasTimer": True,
        "hasEnabledAnswerControl": False,
        "hasVoicemailCue": True,
        "voicemailMatch": "please leave a message",
    }
    audio = DummyAudio(
        rms=0.04,
        continuous_greeting_duration_seconds=8.0,
        beep_detected=True,
        beep_hz_confidence=0.8,
    )

    first = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=1)
    later = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=9)

    assert first.state != DecisionState.VOICEMAIL
    assert later.state == DecisionState.VOICEMAIL
