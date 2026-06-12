from src.detection.call_state_machine import CallStateMachine


class Audio:
    def __init__(self, **kwargs):
        self.rms = kwargs.get("rms", 0.0)
        self.is_silent = kwargs.get("is_silent", True)
        self.has_speech_like = kwargs.get("has_speech_like", False)
        self.ringback_cadence_confidence = kwargs.get("ringback_cadence_confidence", 0.0)
        self.busy_tone_cadence_confidence = kwargs.get("busy_tone_cadence_confidence", 0.0)
        self.speech_duration_seconds = kwargs.get("speech_duration_seconds", 0.0)
        self.silence_duration_seconds = kwargs.get("silence_duration_seconds", 0.0)
        self.continuous_greeting_duration_seconds = kwargs.get("continuous_greeting_duration_seconds", 0.0)
        self.short_speech_burst_detected = kwargs.get("short_speech_burst_detected", False)
        self.human_greeting_detected = kwargs.get("human_greeting_detected", False)
        self.background_noise_level = kwargs.get("background_noise_level", 0.0)
        self.beep_detected = kwargs.get("beep_detected", False)
        self.beep_hz_confidence = kwargs.get("beep_hz_confidence", 0.0)


def transition_path(machine: CallStateMachine) -> list[str]:
    return [entry["new_state"] for entry in machine.get_debug_snapshot()["state_history"]]


def answered_machine() -> CallStateMachine:
    machine = CallStateMachine()
    machine.start_call()
    machine.update_dom({"state": "RINGING", "hasRingingText": True})
    machine.update_dom({"state": "CONNECTED", "hasTimer": True, "hasEnabledHoldButton": True})
    return machine


def test_human_pickup_simulation():
    machine = answered_machine()
    machine.update_audio(
        Audio(
            rms=0.2,
            is_silent=False,
            has_speech_like=True,
            speech_duration_seconds=0.8,
            short_speech_burst_detected=True,
            human_greeting_detected=True,
        )
    )
    machine.update_transcript("Hello?")
    machine.update_timing(answer_elapsed_seconds=1.0)

    assert machine.get_current_state() == "HUMAN"
    assert transition_path(machine) == [
        "DIALING",
        "RINGING",
        "ANSWER_DETECTED",
        "EARLY_ANALYSIS",
        "HUMAN_CANDIDATE",
        "HUMAN",
    ]


def test_voicemail_simulation():
    machine = answered_machine()
    machine.update_audio(
        Audio(
            rms=0.08,
            is_silent=False,
            has_speech_like=True,
            continuous_greeting_duration_seconds=3.0,
        )
    )
    machine.update_transcript("Please leave your message after the tone.")
    machine.update_timing(answer_elapsed_seconds=3.0)

    assert machine.get_current_state() == "VOICEMAIL"
    assert transition_path(machine) == [
        "DIALING",
        "RINGING",
        "ANSWER_DETECTED",
        "EARLY_ANALYSIS",
        "VOICEMAIL_CANDIDATE",
        "VOICEMAIL",
    ]


def test_ivr_simulation():
    machine = answered_machine()
    machine.update_transcript("Press 1 for sales.")
    machine.update_timing(answer_elapsed_seconds=2.5)

    assert machine.get_current_state() == "IVR"
    assert transition_path(machine) == [
        "DIALING",
        "RINGING",
        "ANSWER_DETECTED",
        "EARLY_ANALYSIS",
        "IVR_CANDIDATE",
        "IVR",
    ]


def test_busy_tone_simulation():
    machine = CallStateMachine()
    machine.start_call()
    machine.update_dom({"state": "RINGING", "hasRingingText": True})
    machine.update_audio(
        Audio(
            rms=0.2,
            is_silent=False,
            busy_tone_cadence_confidence=0.9,
        )
    )

    assert machine.get_current_state() == "BUSY"
    assert transition_path(machine) == ["DIALING", "RINGING", "BUSY"]


def test_no_answer_simulation():
    machine = CallStateMachine()
    machine.start_call()
    machine.update_dom({"state": "RINGING", "hasRingingText": True})
    machine.update_timing(elapsed_seconds=56)

    assert machine.get_current_state() == "NO_ANSWER"
    assert transition_path(machine) == ["DIALING", "RINGING", "NO_ANSWER"]


def test_human_is_terminal_and_never_downgrades_to_voicemail():
    machine = answered_machine()
    machine.update_transcript("Hello?")
    machine.update_timing(answer_elapsed_seconds=1.0)
    assert machine.get_current_state() == "HUMAN"

    machine.update_transcript("Please leave your message after the tone.")
    machine.update_audio(Audio(beep_detected=True, beep_hz_confidence=1.0))
    machine.update_timing(answer_elapsed_seconds=4.0)

    assert machine.get_current_state() == "HUMAN"
