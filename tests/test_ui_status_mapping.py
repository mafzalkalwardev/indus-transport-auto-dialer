from autodialer_gui import ui_display_state, ui_state_allows_transition
from src.ui_theme import status_label


def test_connected_like_backend_states_display_connected():
    for state in (
        "CONNECTED",
        "ANSWERED",
        "CONNECTED_AUDIO_EVIDENCE",
        "CONNECTED_MANUAL_CONFIRMATION",
        "HUMAN",
    ):
        assert ui_display_state(state) == "CONNECTED"


def test_connected_label_tells_agent_to_talk_now():
    assert status_label("CONNECTED") == "Call picked up - talk now"
    assert status_label("CONNECTED_AUDIO_EVIDENCE") == "Call picked up - talk now"


def test_answered_pending_displays_classifying_not_connected():
    assert ui_display_state("ANSWERED_PENDING") == "ANSWERED_PENDING"
    assert ui_display_state("CONNECTED_CTRL") == "ANSWERED_PENDING"


def test_basic_call_status_mapping():
    assert ui_display_state("DIALING") == "DIALING"
    assert ui_display_state("CALLING") == "DIALING"
    assert ui_display_state("RINGING") == "RINGING"
    assert ui_display_state("NO_ANSWER") == "NO_ANSWER"
    assert ui_display_state("FAILED") == "FAILED"
    assert ui_display_state("ENDED") == "ENDED"


def test_stale_dialing_and_ringing_cannot_override_connected():
    assert not ui_state_allows_transition("CONNECTED", "DIALING")
    assert not ui_state_allows_transition("CONNECTED_AUDIO_EVIDENCE", "RINGING")
    assert not ui_state_allows_transition("CONNECTED", "FAILED")
    assert not ui_state_allows_transition("CONNECTED", "UNKNOWN")
    assert ui_state_allows_transition("CONNECTED", "ENDED")
    assert ui_state_allows_transition("CONNECTED", "IDLE")
    assert ui_state_allows_transition("DIALING", "CONNECTED_AUDIO_EVIDENCE")
    assert ui_state_allows_transition("RINGING", "ANSWERED_PENDING")
