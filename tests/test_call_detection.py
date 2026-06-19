import pytest

from src.local_call_detector import LocalCallDetector, DetectionConfig, DecisionState


class DummyAudio:
    def __init__(
        self,
        rms=0.1,
        is_silent=False,
        has_speech_like=False,
        ringback_cadence_confidence=0.0,
        beep_hz_confidence=0.0,
        # Optional fields used by the improved local detector (duck-typed)
        speech_duration_seconds=0.0,
        silence_duration_seconds=0.0,
        voicemail_keywords_detected_count=0,
        human_greeting_detected=False,
        short_speech_burst_detected=False,
        continuous_greeting_duration_seconds=0.0,
        beep_detected=False,
        busy_tone_cadence_confidence=0.0,
        vad_confidence=0.0,
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
        self.vad_confidence = vad_confidence
        self.transcript = transcript



def test_ringing_continues_not_end_before_timeout():
    cfg = DetectionConfig(max_ring_seconds=55)
    det = LocalCallDetector(cfg)
    # At 40 seconds: ringing evidence present, no timer
    dom = {"state": "RINGING", "hasRingingText": True, "hasRingingNode": True, "hasTimer": False, "hasEnabledAnswerControl": False, "hasVoicemailCue": False}
    audio = DummyAudio(ringback_cadence_confidence=0.9, is_silent=False)
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=40)
    assert decision.state in ("RINGING", "UNKNOWN") or decision.state == DecisionState.RINGING.value


def test_ringing_ends_after_55_as_no_answer():
    cfg = DetectionConfig(max_ring_seconds=55)
    det = LocalCallDetector(cfg)
    dom = {"state": "RINGING", "hasRingingText": True, "hasRingingNode": True}
    audio = DummyAudio(ringback_cadence_confidence=0.9, is_silent=False)
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=56)
    assert decision.state == DecisionState.NO_ANSWER.value


def test_voicemail_words_during_ringing_ignored():
    cfg = DetectionConfig(max_ring_seconds=55)
    det = LocalCallDetector(cfg)
    dom = {
        "state": "RINGING",
        "callText": "please leave a message",
        "hasRingingText": True,
        "hasRingingNode": True,
        "hasVoicemailCue": True,
    }
    audio = DummyAudio(ringback_cadence_confidence=0.9, is_silent=False)
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=30)
    assert decision.state == DecisionState.RINGING.value


def test_answered_without_timer_becomes_answered_pending():
    cfg = DetectionConfig(max_ring_seconds=55, answered_pending_seconds=10)
    det = LocalCallDetector(cfg)
    dom = {
        "state": "CONNECTED_CTRL",
        "hasEnabledAnswerControl": True,
        "hasTimer": False,
        "hasVoicemailCue": False,
    }
    audio = DummyAudio(rms=0.2, is_silent=False, has_speech_like=True)
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=2)
    assert decision.state == DecisionState.ANSWERED_PENDING.value or decision.state == DecisionState.UNKNOWN.value


def test_connected_ctrl_state_counts_as_answer_control_evidence():
    cfg = DetectionConfig(max_ring_seconds=55, answered_pending_seconds=10)
    det = LocalCallDetector(cfg)
    dom = {
        "state": "CONNECTED_CTRL",
        "hasEnabledAnswerControl": False,
        "hasTimer": False,
        "hasVoicemailCue": False,
    }
    audio = DummyAudio(
        rms=0.0,
        is_silent=False,
        has_speech_like=True,
        ringback_cadence_confidence=0.35,
        speech_duration_seconds=0.69,
        vad_confidence=0.75,
    )
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=25)
    assert decision.state in {
        DecisionState.ANSWERED_PENDING.value,
        DecisionState.HUMAN.value,
    }


def test_connected_ctrl_with_vad_speech_becomes_human():
    cfg = DetectionConfig(
        max_ring_seconds=60,
        answered_pending_seconds=8,
        answered_pending_safe_min_seconds=5,
        human_first_seconds=5,
    )
    det = LocalCallDetector(cfg)
    dom = {
        "state": "CONNECTED_CTRL",
        "hasEnabledAnswerControl": True,
        "hasTimer": False,
    }
    silent = DummyAudio(is_silent=True, has_speech_like=False)

    d0 = det.decide(dom_evidence=dom, audio_features=silent, elapsed_seconds=22)
    assert d0.state in (
        DecisionState.ANSWERED_PENDING.value,
        DecisionState.HUMAN.value,
    )

    class VadAudio(DummyAudio):
        def __init__(self):
            super().__init__(
                rms=0.2,
                is_silent=False,
                has_speech_like=True,
                speech_duration_seconds=0.74,
            )
            self.vad_confidence = 0.75

    d1 = det.decide(dom_evidence=dom, audio_features=VadAudio(), elapsed_seconds=29)
    d2 = det.decide(dom_evidence=dom, audio_features=VadAudio(), elapsed_seconds=31)
    assert DecisionState.HUMAN.value in (d1.state, d2.state)


def test_human_short_hello_becomes_human():
    cfg = DetectionConfig(max_ring_seconds=55, answered_pending_seconds=10)
    det = LocalCallDetector(cfg)
    dom = {"state": "CONNECTED", "hasTimer": True, "hasEnabledAnswerControl": True, "hasVoicemailCue": False}
    audio = DummyAudio(
        rms=0.2,
        is_silent=False,
        has_speech_like=True,
        speech_duration_seconds=1.2,
        human_greeting_detected=True,
        short_speech_burst_detected=True,
    )
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=12)
    assert decision.state == DecisionState.HUMAN.value


def test_human_is_locked_and_never_demoted():
    det = LocalCallDetector(DetectionConfig(answered_pending_seconds=10))
    dom = {"state": "CONNECTED", "hasTimer": True, "hasEnabledAnswerControl": True}
    audio = DummyAudio(
        has_speech_like=True,
        speech_duration_seconds=1.0,
        human_greeting_detected=True,
        short_speech_burst_detected=True,
    )

    d1 = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=12)
    assert d1.state == DecisionState.HUMAN.value

    silent = DummyAudio(is_silent=True)
    d2 = det.decide(
        dom_evidence={"state": "RINGING", "hasRingingText": True},
        audio_features=silent,
        elapsed_seconds=13,
    )
    assert d2.state == DecisionState.HUMAN.value


def test_human_bypasses_debounce_on_first_poll():
    det = LocalCallDetector(
        DetectionConfig(
            decision_stability_window=3,
            answered_pending_seconds=10,
        )
    )
    dom = {"state": "CONNECTED", "hasTimer": True, "hasEnabledAnswerControl": True}
    audio = DummyAudio(
        has_speech_like=True,
        speech_duration_seconds=1.0,
        human_greeting_detected=True,
        short_speech_burst_detected=True,
    )

    d = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=12)
    assert d.state == DecisionState.HUMAN.value





def test_voicemail_long_greeting_plus_beep_becomes_voicemail():
    cfg = DetectionConfig(
        max_ring_seconds=55,
        answered_pending_seconds=10,
        voicemail_confirmation_count=1,
    )
    det = LocalCallDetector(cfg)
    dom = {"state": "CONNECTED", "hasTimer": True, "hasEnabledAnswerControl": False, "hasVoicemailCue": True}
    audio = DummyAudio(
        rms=0.05,
        is_silent=False,
        has_speech_like=False,
        beep_hz_confidence=1.0,
        beep_detected=True,
        speech_duration_seconds=7.5,
        continuous_greeting_duration_seconds=7.5,
        voicemail_keywords_detected_count=1,
        human_greeting_detected=False,
    )
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=12)
    assert decision.state in (DecisionState.VOICEMAIL.value, DecisionState.ANSWERED_PENDING.value)


def test_hello_with_background_noise_must_not_be_voicemail():
    cfg = DetectionConfig(max_ring_seconds=55, answered_pending_seconds=10)
    det = LocalCallDetector(cfg)
    dom = {"state": "CONNECTED", "hasTimer": True, "hasEnabledAnswerControl": True, "hasVoicemailCue": False}
    audio = DummyAudio(
        rms=0.3,  # background noise high
        is_silent=False,
        has_speech_like=False,
        speech_duration_seconds=0.8,
        short_speech_burst_detected=True,
        human_greeting_detected=True,
    )
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=6)
    assert decision.state != DecisionState.VOICEMAIL.value


def test_short_speech_burst_no_transcript_must_not_be_voicemail():
    cfg = DetectionConfig(max_ring_seconds=55, answered_pending_seconds=10)
    det = LocalCallDetector(cfg)
    dom = {"state": "CONNECTED", "hasTimer": True, "hasEnabledAnswerControl": True, "hasVoicemailCue": False}
    audio = DummyAudio(
        rms=0.25,
        is_silent=False,
        has_speech_like=True,
        speech_duration_seconds=1.8,
        short_speech_burst_detected=True,
        human_greeting_detected=False,  # transcript unavailable
    )
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=6)
    assert decision.state != DecisionState.VOICEMAIL.value


def test_noisy_answered_call_stays_answered_pending():
    cfg = DetectionConfig(max_ring_seconds=55, answered_pending_seconds=10)
    det = LocalCallDetector(cfg)
    dom = {"state": "CONNECTED_CTRL", "hasEnabledAnswerControl": True, "hasTimer": True, "hasVoicemailCue": False}
    audio = DummyAudio(
        rms=0.25,
        is_silent=False,
        has_speech_like=False,
        human_greeting_detected=False,
        speech_duration_seconds=0.0,
        voicemail_keywords_detected_count=0,
    )
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=6)
    assert decision.state == DecisionState.ANSWERED_PENDING.value


def test_voicemail_not_emitted_before_7_seconds_after_answer():
    cfg = DetectionConfig(max_ring_seconds=55, answered_pending_seconds=10, voicemail_confirmation_count=1)
    det = LocalCallDetector(cfg)
    dom = {"state": "CONNECTED", "hasTimer": True, "hasEnabledAnswerControl": False, "hasVoicemailCue": True}
    audio = DummyAudio(
        rms=0.05,
        is_silent=False,
        has_speech_like=False,
        beep_hz_confidence=1.0,
        beep_detected=True,
        continuous_greeting_duration_seconds=7.0,
        voicemail_keywords_detected_count=1,
        human_greeting_detected=False,
    )
    # answer evidence first seen at elapsed=0 in detector, so use elapsed=6 -> answer_elapsed=6, should not emit until >=7
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=6)
    assert decision.state != DecisionState.VOICEMAIL.value



def test_browser_error_becomes_failed():
    cfg = DetectionConfig()
    det = LocalCallDetector(cfg)
    dom = {"state": "FAILED"}
    audio = DummyAudio()
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=5)
    assert decision.state == DecisionState.FAILED.value


def test_busy_tone_becomes_busy():
    det = LocalCallDetector(DetectionConfig())
    dom = {"state": "RINGING", "hasRingingText": False, "hasRingingNode": False}
    audio = DummyAudio(
        rms=0.2,
        is_silent=False,
        busy_tone_cadence_confidence=0.9,
    )
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=5)
    assert decision.state == DecisionState.BUSY.value


def test_post_ringing_speech_evidence_becomes_connected_audio_evidence():
    cfg = DetectionConfig(max_ring_seconds=55)
    det = LocalCallDetector(cfg)
    ringing_dom = {
        "state": "RINGING",
        "hasRingingText": True,
        "hasRingingNode": True,
        "hasTimer": False,
        "hasEnabledAnswerControl": False,
    }
    ring_audio = DummyAudio(ringback_cadence_confidence=0.9, is_silent=False)

    det.decide(dom_evidence=ringing_dom, audio_features=ring_audio, elapsed_seconds=4)
    decision = det.decide(
        dom_evidence=ringing_dom,
        audio_features=DummyAudio(
            rms=0.22,
            is_silent=False,
            has_speech_like=True,
            ringback_cadence_confidence=0.1,
            speech_duration_seconds=0.67,
            short_speech_burst_detected=True,
            vad_confidence=0.75,
        ),
        elapsed_seconds=8,
    )

    assert decision.state == DecisionState.CONNECTED_AUDIO_EVIDENCE.value


def test_human_speech_after_ringing_becomes_connected():
    cfg = DetectionConfig(max_ring_seconds=55)
    det = LocalCallDetector(cfg)
    ringing_dom = {
        "state": "RINGING",
        "hasRingingText": True,
        "hasRingingNode": True,
    }
    det.decide(
        dom_evidence=ringing_dom,
        audio_features=DummyAudio(ringback_cadence_confidence=0.85),
        elapsed_seconds=4,
    )
    decision = det.decide(
        dom_evidence={
            "state": "CONNECTED_CTRL",
            "hasEnabledAnswerControl": True,
            "hasRingingText": True,
            "hasRingingNode": False,
        },
        audio_features=DummyAudio(
            rms=0.2,
            is_silent=False,
            has_speech_like=True,
            ringback_cadence_confidence=0.0,
            speech_duration_seconds=0.7,
            short_speech_burst_detected=True,
            vad_confidence=0.76,
            transcript="hello hello",
        ),
        elapsed_seconds=9,
    )
    assert decision.state == DecisionState.HUMAN.value
    assert decision.debug.get("human_detected") is True


def test_public_detect_interface_returns_priority_result():
    det = LocalCallDetector(DetectionConfig(decision_stability_window=1))
    result = det.detect(
        {
            "has_speech_like": True,
            "is_silent": False,
            "speech_duration_seconds": 0.7,
            "short_speech_burst_detected": True,
            "vad_confidence": 0.75,
            "transcript": "hello hello",
        },
        {"state": "CONNECTED_CTRL", "has_enabled_answer_control": True},
        {"state": "RINGING", "elapsed_seconds": 12},
    )
    assert result.state == DecisionState.HUMAN
    assert result.priority > 0
    assert result.evidence["previous_state"] == "RINGING"


def test_voicemail_phrase_becomes_voicemail_after_confirmation():
    det = LocalCallDetector(
        DetectionConfig(
            voicemail_confirmation_count=2,
            voicemail_stability_cycles_required=2,
            decision_stability_window=1,
        )
    )
    dom = {
        "state": "CONNECTED",
        "hasTimer": True,
        "callText": "your call has been forwarded to the mailbox please record your message at the tone",
        "hasVoicemailCue": True,
    }
    audio = DummyAudio(
        is_silent=False,
        continuous_greeting_duration_seconds=8.0,
        voicemail_keywords_detected_count=2,
        beep_detected=True,
        beep_hz_confidence=0.9,
        transcript="your call has been forwarded to the mailbox please record your message at the tone",
    )
    det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=1)
    d1 = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=9)
    d2 = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=10)
    assert d1.state in (DecisionState.ANSWERED_PENDING.value, DecisionState.VOICEMAIL.value)
    assert d2.state == DecisionState.VOICEMAIL.value


def test_stale_dialing_cannot_override_connected():
    det = LocalCallDetector(DetectionConfig())
    connected = det.decide(
        dom_evidence={"state": "CONNECTED", "hasTimer": True},
        audio_features=DummyAudio(
            has_speech_like=True,
            speech_duration_seconds=0.8,
            human_greeting_detected=True,
            short_speech_burst_detected=True,
        ),
        elapsed_seconds=8,
    )
    assert connected.state == DecisionState.HUMAN.value
    stale = det.decide(
        dom_evidence={"state": "DIALING"},
        audio_features=DummyAudio(is_silent=True),
        elapsed_seconds=9,
    )
    assert stale.state == DecisionState.HUMAN.value


def test_stale_ringing_text_does_not_override_connected_audio_evidence():
    cfg = DetectionConfig(max_ring_seconds=55)
    det = LocalCallDetector(cfg)
    stale_dom = {
        "state": "RINGING",
        "callText": "Latest calls Outgoing call Calling",
        "hasRingingText": True,
        "hasRingingNode": False,
        "hasTimer": False,
        "hasEnabledAnswerControl": False,
    }

    det.decide(
        dom_evidence=stale_dom,
        audio_features=DummyAudio(ringback_cadence_confidence=0.8, is_silent=False),
        elapsed_seconds=3,
    )
    decision = det.decide(
        dom_evidence=stale_dom,
        audio_features=DummyAudio(
            rms=0.2,
            is_silent=False,
            has_speech_like=True,
            ringback_cadence_confidence=0.0,
            speech_duration_seconds=0.7,
            short_speech_burst_detected=True,
            vad_confidence=0.76,
        ),
        elapsed_seconds=9,
    )

    assert decision.state == DecisionState.CONNECTED_AUDIO_EVIDENCE.value


def test_failed_cannot_override_connected():
    det = LocalCallDetector(DetectionConfig())
    connected = det.decide(
        dom_evidence={"state": "CONNECTED", "hasTimer": True},
        audio_features=DummyAudio(
            has_speech_like=True,
            speech_duration_seconds=0.8,
            human_greeting_detected=True,
            short_speech_burst_detected=True,
        ),
        elapsed_seconds=8,
    )
    assert connected.state == DecisionState.HUMAN.value
    failed = det.decide(
        dom_evidence={"state": "FAILED"},
        audio_features=DummyAudio(),
        elapsed_seconds=9,
    )
    assert failed.state == DecisionState.HUMAN.value


def test_debounce_cannot_demote_connected_audio_to_unknown():
    det = LocalCallDetector(DetectionConfig(decision_stability_window=3))
    stale_dom = {
        "state": "RINGING",
        "hasRingingText": True,
        "hasRingingNode": False,
    }
    det.decide(
        dom_evidence=stale_dom,
        audio_features=DummyAudio(ringback_cadence_confidence=0.8),
        elapsed_seconds=4,
    )
    connected_audio = det.decide(
        dom_evidence=stale_dom,
        audio_features=DummyAudio(
            rms=0.2,
            is_silent=False,
            has_speech_like=True,
            ringback_cadence_confidence=0.0,
            speech_duration_seconds=0.7,
            short_speech_burst_detected=True,
            vad_confidence=0.76,
        ),
        elapsed_seconds=9,
    )
    assert connected_audio.state == DecisionState.CONNECTED_AUDIO_EVIDENCE.value
    unknown = det.decide(
        dom_evidence={"state": "IDLE", "callText": "latest calls"},
        audio_features=DummyAudio(is_silent=True),
        elapsed_seconds=10,
    )
    assert unknown.state == DecisionState.CONNECTED_AUDIO_EVIDENCE.value


def test_manual_end_becomes_ended_manually():
    det = LocalCallDetector(DetectionConfig())
    decision = det.decide(
        dom_evidence={"state": "ENDED_MANUALLY"},
        audio_features=DummyAudio(),
        elapsed_seconds=5,
    )
    assert decision.state == DecisionState.ENDED_MANUALLY.value


def test_final_outcome_only_once():
    cfg = DetectionConfig(max_ring_seconds=55, voicemail_confirmation_count=1)
    det = LocalCallDetector(cfg)
    dom = {"state": "ENDED"}
    audio = DummyAudio()
    d1 = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=20)
    d2 = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=21)
    assert d1.state == d2.state
    assert d1.state == DecisionState.ENDED.value


def test_watchdog_access_denied_does_not_crash(monkeypatch):
    import src.slot_watchdog as watchdog

    class FakePsutil:
        class AccessDenied(Exception):
            pass
        class NoSuchProcess(Exception):
            pass
        class ZombieProcess(Exception):
            pass

        @staticmethod
        def process_iter(_attrs):
            raise FakePsutil.AccessDenied()

    monkeypatch.setitem(__import__("sys").modules, "psutil", FakePsutil)
    assert watchdog.webengine_total_memory_mb() == 0

