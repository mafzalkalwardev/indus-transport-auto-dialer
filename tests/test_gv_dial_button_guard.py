from PyQt6.QtWidgets import QApplication, QWidget

from PyQt6.QtCore import QUrl

from src.gv_controller import GVController


def _controller_for(phone: str) -> GVController:
    ctrl = GVController.__new__(GVController)
    ctrl._pending_dial_phone = phone
    ctrl._current_call_phone = phone
    ctrl._calls_ready_attempts = 0
    ctrl._idle_count = 0
    ctrl._vm_count = 0
    ctrl._ctrl_count = 0
    ctrl._amd_answer_at = 0.0
    ctrl._amd_decision_ms = 0
    ctrl._dial_started_at = 0.0
    ctrl._state = "IDLE"
    ctrl._active_call = False
    ctrl._whisper_pending = False
    ctrl._force_native_number_entry = False
    ctrl._native_submit_scheduled = False
    ctrl._call_clicked_at = 0.0
    ctrl._awaiting_call_panel_since = 0.0
    ctrl._dial_url_variant = 0
    ctrl._native_key_attempts = 0
    ctrl._native_key_attempted = False
    ctrl._load_ok = False
    ctrl._load_retry_count = 0
    ctrl._logged_in = False
    ctrl._login_required_logged = False
    ctrl._autofill_paused = False
    ctrl._email_step_done = False
    ctrl._last_login_fill_status = ""
    ctrl._redirected_to_signin = False
    ctrl._setup_mode = False
    ctrl._state_diag_seen = set()
    ctrl._console_messages = []
    ctrl._render_w = 800
    ctrl._render_h = 600
    ctrl._min_answer_seconds = 10.0
    ctrl._dial_stuck_timer = None
    return ctrl


class _FakeView:
    def width(self):
        return 1200

    def height(self):
        return 800

    def setFocus(self):
        pass

    def activateWindow(self):
        pass


class _FakeUrl:
    def __init__(self, value):
        self._value = value

    def toString(self):
        return self._value


class _FakePage:
    def __init__(self, url):
        self._url = url
        self.loaded = []
        self.js = []

    def url(self):
        return _FakeUrl(self._url)

    def load(self, url):
        if isinstance(url, QUrl):
            self.loaded.append(url.toString())
        else:
            self.loaded.append(str(url))

    def runJavaScript(self, js, callback=None):
        self.js.append(js)
        if callback:
            callback(None)


def test_call_button_status_rejects_stale_different_number():
    ctrl = _controller_for("+12392849055")

    assert not ctrl._call_button_status_matches_pending(
        "call_button_ready|x=1220|y=165|aria=Call + 1 8 1 5 3 8 5 8 0 0 0|text=call"
    )


def test_call_button_status_accepts_matching_number():
    ctrl = _controller_for("+12392849055")

    assert ctrl._call_button_status_matches_pending(
        "call_button_ready|x=1220|y=165|aria=Call +1 239 284 9055|text=call"
    )


def test_call_button_status_rejects_generic_call_button_without_target_proof():
    ctrl = _controller_for("+12392849055")

    assert not ctrl._call_button_status_matches_pending(
        "call_button_ready|x=1220|y=165|aria=Call|text=call"
    )


def test_call_button_status_accepts_generic_call_button_with_matching_input():
    ctrl = _controller_for("+12392849055")

    assert ctrl._call_button_status_matches_pending(
        "call_button_ready|x=1220|y=165|input_digits=12392849055|aria=Call|text=call"
    )


def test_call_suggestion_status_must_match_pending_number():
    ctrl = _controller_for("+12392849055")

    assert ctrl._call_button_status_matches_pending(
        "call_suggestion_ready|x=830|y=315|input_digits=12392849055|text=Call with +1 239 284 9055"
    )
    assert not ctrl._call_button_status_matches_pending(
        "call_suggestion_ready|x=830|y=315|input_digits=18153858000|text=Call with +1 815 385 8000"
    )


def test_audio_backend_unavailable_enables_dom_pickup_fallback():
    class Features:
        def __init__(self, status):
            self.backend_status = status

    assert GVController._audio_detection_unavailable(Features("NO_BACKEND"))
    assert GVController._audio_detection_unavailable(Features("OFF"))
    assert not GVController._audio_detection_unavailable(Features("UNKNOWN"))
    assert not GVController._audio_detection_unavailable(Features("ON"))


def test_call_button_click_uses_js_activation_before_native_click():
    ctrl = _controller_for("+12392849055")
    calls = []
    logs = []
    ctrl._capture_dial_diagnostics = lambda label: calls.append(("capture", label))
    ctrl._focus_target_call_button = lambda: False
    ctrl._activate_target_call_button_js = lambda: calls.append(("activate", None)) or True
    ctrl._native_click_view_coords = lambda x, y: calls.append(("native", x, y)) or True
    ctrl._emit_log = logs.append

    assert ctrl._click_call_button_from_status(
        "call_button_ready|x=964|y=165|input_digits=12392849055|aria=Call +1 239 284 9055|text=call"
    )
    assert ("activate", None) in calls
    assert ("native", 964, 165) in calls
    assert calls.index(("activate", None)) < calls.index(("native", 964, 165))
    assert "Dial UI status: call_button_focus_failed" in logs
    assert "Dial UI status: call_button_clicked_js" in logs


def test_js_clicked_call_button_status_accepts_matching_number():
    ctrl = _controller_for("+17085681794")

    assert ctrl._call_button_status_matches_pending(
        "call_button_clicked_js|x=1220|y=164|aria=Call + 1 7 0 8 5 6 8 1 7 9 4|text=call"
    )


def test_click_view_coords_uses_webengine_view():
    app = QApplication.instance() or QApplication([])
    ctrl = _controller_for("+19097202727")
    ctrl.view = QWidget()
    ctrl.view.resize(1200, 800)
    ctrl._emit_log = lambda _msg: None

    assert ctrl._click_view_coords(400, 300)
    assert not ctrl._click_view_coords(-1, 300)
    assert not ctrl._click_view_coords(2000, 300)
    assert app is not None


def test_gv_dial_url_variants():
    from src.gv_controller import _gv_dial_url_variants

    urls = _gv_dial_url_variants("+19097202727")
    assert any("a=nc" in u for u in urls)
    assert any("/dial/" in u for u in urls)


def test_offscreen_native_key_target_does_not_consume_attempt():
    ctrl = _controller_for("+17085681794")
    ctrl.view = _FakeView()
    ctrl._native_key_attempts = 0
    ctrl._native_key_attempted = False
    ctrl._emit_log = lambda _msg: None

    assert not ctrl._type_number_from_status(
        "input_needs_native_keys|reason=disabled|x=966|y=-131|input=INPUT"
    )
    assert ctrl._native_key_attempts == 0
    assert ctrl._native_key_attempted is False


def test_ready_for_dial_js_called_without_reload_on_voice_page(monkeypatch):
    """On voice.google.com the controller should call _JS_READY_FOR_DIAL, not reload."""
    scheduled = []
    monkeypatch.setattr(
        "src.gv_controller.QTimer.singleShot",
        lambda ms, fn: scheduled.append((ms, fn)),
    )
    ctrl = _controller_for("+17085681794")
    ctrl._active_call = True
    ctrl._pending_dial_phone = "+17085681794"
    ctrl._current_call_phone = "+17085681794"
    ctrl._page = _FakePage("https://voice.google.com/u/0/calls")
    ctrl._emit_log = lambda _msg: None

    ctrl._ensure_calls_page_then_dial()

    # No page reload — _JS_READY_FOR_DIAL is dispatched immediately.
    assert ctrl._page.loaded == []
    assert ctrl._page.js
    assert "ready" in ctrl._page.js[-1]


def test_first_dial_attempt_loads_calls_page_only_when_off_voice(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "src.gv_controller.QTimer.singleShot",
        lambda ms, fn: scheduled.append((ms, fn)),
    )
    ctrl = _controller_for("+17085681794")
    ctrl._active_call = True
    ctrl._pending_dial_phone = "+17085681794"
    ctrl._current_call_phone = "+17085681794"
    ctrl._dial_url_variant = 0
    ctrl._dial_step_attempts = 0
    ctrl._page = _FakePage("about:blank")
    ctrl._emit_log = lambda _msg: None

    ctrl._ensure_calls_page_then_dial()

    assert ctrl._page.loaded == ["https://voice.google.com/u/0/calls?a=nc,%2B17085681794"]
    assert scheduled and scheduled[-1][0] == 2500


def test_disabled_native_field_waits_before_alternate_dial_url(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "src.gv_controller.QTimer.singleShot",
        lambda ms, fn: scheduled.append((ms, fn)),
    )
    ctrl = _controller_for("+17085681794")
    ctrl._active_call = True
    ctrl._pending_dial_phone = "+17085681794"
    ctrl._current_call_phone = "+17085681794"
    ctrl._dial_url_variant = 0
    ctrl._native_key_attempted = False
    ctrl._dial_step_attempts = 4
    ctrl._page = _FakePage("https://voice.google.com/u/0/calls")
    ctrl._emit_log = lambda _msg: None

    ctrl._handle_retryable_dial_status("call_button_missing")

    assert ctrl._dial_url_variant == 0
    assert ctrl._page.loaded == []
    assert scheduled and scheduled[-1][0] == 900


def test_disabled_target_button_eventually_falls_back_to_direct_dial_url(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "src.gv_controller.QTimer.singleShot",
        lambda ms, fn: scheduled.append((ms, fn)),
    )
    ctrl = _controller_for("+17085681794")
    ctrl._active_call = True
    ctrl._pending_dial_phone = "+17085681794"
    ctrl._current_call_phone = "+17085681794"
    ctrl._dial_url_variant = 0
    ctrl._dial_step_attempts = 18  # Now requires 15+ attempts before rotation
    ctrl._page = _FakePage("https://voice.google.com/dial/+17085681794")
    ctrl._emit_log = lambda _msg: None
    ctrl._mark_call_click_pending = lambda: None

    ctrl._page.runJavaScript = lambda js, cb: cb(False) if cb else None

    ctrl._handle_retryable_dial_status("call_button_disabled_for_target")

    assert ctrl._dial_url_variant == 1
    assert ctrl._page.loaded == ["https://voice.google.com/u/0/calls"]
    assert scheduled and scheduled[-1][0] == 2500


def test_native_keypad_status_clicks_each_digit():
    ctrl = _controller_for("+17085681794")
    ctrl.view = _FakeView()
    ctrl._native_key_attempts = 0
    ctrl._native_key_attempted = False
    ctrl._emit_log = lambda _msg: None
    ctrl._page = _FakePage("https://voice.google.com/u/0/calls")
    ctrl._clear_dial_field_before_native_input = lambda _status: True
    clicked = []
    ctrl._click_view_coords = lambda x, y: clicked.append((x, y)) or True

    assert ctrl._click_keypad_from_status(
        "keypad_needs_native_clicks|reason=disabled|input=4,5|coords=7,10,20;0,30,40;8,50,60;5,70,80;6,90,100;8,110,120;1,130,140;7,150,160;9,170,180;4,190,200"
    )
    assert clicked == [(10, 20), (30, 40), (50, 60), (70, 80), (90, 100), (110, 120), (130, 140), (150, 160), (170, 180), (190, 200)]


def test_native_keypad_does_not_append_when_clear_fails():
    ctrl = _controller_for("+17085681794")
    ctrl.view = _FakeView()
    ctrl._native_key_attempts = 0
    ctrl._native_key_attempted = False
    ctrl._emit_log = lambda _msg: None
    ctrl._page = _FakePage("https://voice.google.com/u/0/calls")
    ctrl._clear_dial_field_before_native_input = lambda _status: False
    clicked = []
    ctrl._click_view_coords = lambda x, y: clicked.append((x, y)) or True

    assert not ctrl._click_keypad_from_status(
        "keypad_needs_native_clicks|reason=disabled|input=4,5|coords=7,10,20;0,30,40;8,50,60;5,70,80;6,90,100;8,110,120;1,130,140;7,150,160;9,170,180;4,190,200"
    )
    assert clicked == []


def test_js_dial_supports_click_only_mode():
    from src.gv_controller import _js_dial

    js = _js_dial("+17085681794", click_only=True)
    assert "clickOnly=true" in js
    assert "numberLooksEntered" in js
    assert "current === digits || current === dialDigits" in js
    assert "return inputReflectsDigits;" in js
    assert "return clickedDigits || inputReflectsDigits" not in js


def test_js_dial_does_not_synthetic_click_final_call_button():
    from src.gv_controller import _js_dial

    js = _js_dial("+17085681794")

    assert "call_button_ready|x=" in js
    assert "call_button_clicked_js" not in js


def test_clear_dial_field_reports_remaining_digits():
    from src.gv_controller import _JS_CLEAR_DIAL_FIELD

    assert "clear_failed|value=" in _JS_CLEAR_DIAL_FIELD
    assert "shadowRoot" in _JS_CLEAR_DIAL_FIELD


def test_call_detector_treats_idle_keypad_page_as_idle():
    from src.gv_controller import _JS_ACTIVE_CALL_PRESENT, _JS_DETECT_STATE

    assert "idleDialpadPage" in _JS_DETECT_STATE
    assert "you're all caught up" in _JS_DETECT_STATE
    assert "enter a name or number" in _JS_DETECT_STATE
    assert "idleDialpadPage" in _JS_ACTIVE_CALL_PRESENT
    assert "if(idleDialpadPage) return false;" in _JS_ACTIVE_CALL_PRESENT


def test_retry_start_call_does_not_reenter_number(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "src.gv_controller.QTimer.singleShot",
        lambda ms, fn: scheduled.append(fn),
    )
    ctrl = _controller_for("+17085681794")
    ctrl._active_call = True
    ctrl._current_call_phone = "+17085681794"
    ctrl._page = _FakePage("https://voice.google.com/u/0/calls")
    ctrl._emit_log = lambda _msg: None

    ctrl.retry_start_call()

    assert all(getattr(fn, "__name__", "") != "_dial_step" for fn in scheduled)


def test_dial_step_waits_for_recent_call_panel_after_click():
    ctrl = _controller_for("+17085681794")
    ctrl._active_call = True
    ctrl._pending_dial_phone = "+17085681794"
    ctrl._page = _FakePage("https://voice.google.com/u/0/calls")
    ctrl._dial_step_attempts = 0
    ctrl._force_native_number_entry = False
    ctrl._mark_call_click_pending()

    ctrl._dial_step()

    assert ctrl._dial_step_attempts == 0
    assert ctrl._page.js == []


def test_call_click_pending_does_not_promote_to_ringing_before_panel_opens():
    ctrl = _controller_for("+17085681794")
    ctrl._state = "DIALING"
    states = []
    ctrl._set_state = states.append

    ctrl._mark_call_click_pending()

    assert states == []
    assert ctrl._call_clicked_at > 0
    assert ctrl._awaiting_call_panel_since == ctrl._call_clicked_at


def test_call_panel_confirmation_emits_ringing_before_polling(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "src.gv_controller.QTimer.singleShot",
        lambda ms, fn: scheduled.append((ms, fn)),
    )

    class ActivePage(_FakePage):
        def runJavaScript(self, js, callback=None):
            self.js.append(js)
            if callback:
                callback(True)

    ctrl = _controller_for("+17085681794")
    ctrl._active_call = True
    ctrl._state = "DIALING"
    ctrl._pending_dial_phone = "+17085681794"
    ctrl._call_start_verify_attempts = 1
    ctrl._awaiting_call_panel_since = 123.0
    ctrl._page = ActivePage("https://voice.google.com/u/0/calls")
    ctrl._page_alive = lambda: True
    ctrl._emit_log = lambda _msg: None
    states = []
    ctrl._set_state = states.append
    ctrl._poll_once = lambda: None
    ctrl.start_polling = lambda: None

    ctrl._verify_call_started_after_click()

    assert ctrl._pending_dial_phone == ""
    assert ctrl._awaiting_call_panel_since == 0.0
    assert states == ["RINGING"]
    assert [ms for ms, _fn in scheduled] == [200, 900]


def test_dom_idle_overrides_sticky_human_after_connected_call():
    class Signal:
        def __init__(self):
            self.items = []

        def emit(self, *args):
            self.items.append(args)

    class AudioMonitor:
        last_features = None

        def poll(self):
            return None

    class StickyHumanEngine:
        def update(self, **_kwargs):
            return type(
                "Decision",
                (),
                {
                    "state": "HUMAN",
                    "confidence": 1.0,
                    "reason": "human pickup locked",
                    "debug": {},
                },
            )()

    ctrl = _controller_for("+17085681794")
    ctrl._active_call = True
    ctrl._state = "CONNECTED"
    ctrl._runtime_cfg = {}
    ctrl._audio_monitor = AudioMonitor()
    ctrl._decision_engine = StickyHumanEngine()
    from src.call_state_engine import CallStateEngine

    ctrl._call_state_engine = CallStateEngine()
    ctrl._dial_started_at = 1.0
    ctrl._current_call_phone = "+17085681794"
    ctrl._pending_dial_phone = ""
    ctrl._amd_answer_at = 1.0
    ctrl._amd_decision_ms = 0
    ctrl._idle_count = 0
    ctrl._vm_count = 0
    ctrl._ctrl_count = 0
    ctrl._dial_stuck_timer = None
    ctrl.slot_id = 0
    ctrl._page = _FakePage("https://voice.google.com/u/0/calls")
    ctrl._page_alive = lambda: True
    ctrl._pulse_heartbeat = lambda: None
    ctrl.stop_polling = lambda: None
    ctrl._emit_log = lambda _msg: None
    ctrl.detection_update = Signal()
    states = []
    ctrl._set_state = states.append

    ctrl._on_poll_result({"state": "IDLE", "callText": "latest calls you're all caught up"})

    assert states == ["ENDED"]


def test_non_manual_hangup_emits_ended_from_connected(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "src.gv_controller.QTimer.singleShot",
        lambda ms, fn: scheduled.append((ms, fn)),
    )
    ctrl = _controller_for("+17085681794")
    ctrl._state = "CONNECTED"
    ctrl._active_call = True
    ctrl._pending_dial_phone = ""
    ctrl._current_call_phone = "+17085681794"
    ctrl._force_native_number_entry = True
    ctrl._native_submit_scheduled = True
    ctrl._call_clicked_at = 1.0
    ctrl._amd_answer_at = 1.0
    ctrl._amd_decision_ms = 123
    ctrl._whisper_pending = True
    ctrl._dial_stuck_timer = None
    ctrl._page = _FakePage("https://voice.google.com/u/0/calls")
    ctrl._page_alive = lambda: True
    ctrl.stop_polling = lambda: None
    ctrl._emit_log = lambda _msg: None
    states = []
    ctrl._set_state = states.append

    ctrl.hangup()

    assert states == ["ENDED"]
    assert ctrl._current_call_phone == ""
    assert scheduled and scheduled[-1][0] == 1000


def test_keypad_with_blue_call_button_does_not_trigger_active_call():
    """Keypad page with number entered and blue call button must NOT be detected as active call."""
    from src.gv_controller import _JS_ACTIVE_CALL_PRESENT

    # Simulate a keypad page body text: number entered, blue call button visible, no hang-up button
    fake_result = {
        "state": "IDLE",
        "callText": "enter a name or number +1 239 284 9055 call",
        "idleDialpadPage": False,
        "hasRingingText": False,
        "hasRingingNode": False,
        "hasTimer": False,
        "hasEnabledAnswerControl": False,
    }
    # The JS function _JS_ACTIVE_CALL_PRESENT should return false for this scenario
    # because there's no hang-up button, no timer, no in-call controls, and the idleDialpadPage
    # check catches it first.
    # We verify by checking the JS source contains the idleDialpadPage guard.
    assert "idleDialpadPage" in _JS_ACTIVE_CALL_PRESENT
    assert "if(idleDialpadPage) return false;" in _JS_ACTIVE_CALL_PRESENT
    # And the old loose ringing/calling text check is gone:
    assert "body.indexOf('ringing')" not in _JS_ACTIVE_CALL_PRESENT
    assert "body.indexOf('calling')" not in _JS_ACTIVE_CALL_PRESENT


def test_url_variant_stays_zero_during_routine_retries(monkeypatch):
    """URL variant should NOT rotate during normal retry attempts (only after 15+ failures)."""
    scheduled = []
    monkeypatch.setattr(
        "src.gv_controller.QTimer.singleShot",
        lambda ms, fn: scheduled.append((ms, fn)),
    )
    ctrl = _controller_for("+17085681794")
    ctrl._active_call = True
    ctrl._pending_dial_phone = "+17085681794"
    ctrl._current_call_phone = "+17085681794"
    ctrl._dial_url_variant = 0
    ctrl._dial_step_attempts = 10  # Less than 15 — should NOT rotate
    ctrl._page = _FakePage("https://voice.google.com/u/0/calls")
    ctrl._page_alive = lambda: True
    ctrl._emit_log = lambda _msg: None
    ctrl._mark_call_click_pending = lambda: None

    # Simulate _JS_ACTIVE_CALL_PRESENT returning False (no panel)
    ctrl._page.runJavaScript = lambda js, cb: cb(False) if cb else None

    ctrl._handle_retryable_dial_status("call_button_missing")

    # Should still be on variant 0, and should schedule another retry (not URL reload)
    assert ctrl._dial_url_variant == 0
    assert ctrl._page.loaded == []
    assert scheduled and scheduled[-1][0] == 900


def test_url_variant_rotates_after_sustained_failure(monkeypatch):
    """URL variant should rotate after 15+ attempts with sustained failure."""
    scheduled = []
    monkeypatch.setattr(
        "src.gv_controller.QTimer.singleShot",
        lambda ms, fn: scheduled.append((ms, fn)),
    )
    ctrl = _controller_for("+17085681794")
    ctrl._active_call = True
    ctrl._pending_dial_phone = "+17085681794"
    ctrl._current_call_phone = "+17085681794"
    ctrl._dial_url_variant = 0
    ctrl._dial_step_attempts = 18  # >= 15 and % 6 == 0 — should rotate
    ctrl._page = _FakePage("https://voice.google.com/u/0/calls")
    ctrl._page_alive = lambda: True
    ctrl._emit_log = lambda _msg: None
    ctrl._mark_call_click_pending = lambda: None

    ctrl._page.runJavaScript = lambda js, cb: cb(False) if cb else None

    ctrl._handle_retryable_dial_status("call_button_missing")

    assert ctrl._dial_url_variant == 1
    assert ctrl._page.loaded == ["https://voice.google.com/u/0/calls"]
    assert scheduled and scheduled[-1][0] == 2500
