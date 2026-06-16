from PyQt6.QtWidgets import QApplication, QWidget

from PyQt6.QtCore import QUrl

from src.gv_controller import GVController


def _controller_for(phone: str) -> GVController:
    ctrl = GVController.__new__(GVController)
    ctrl._pending_dial_phone = phone
    ctrl._current_call_phone = phone
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


def test_call_button_status_accepts_generic_call_button():
    ctrl = _controller_for("+12392849055")

    assert ctrl._call_button_status_matches_pending(
        "call_button_ready|x=1220|y=165|aria=Call|text=call"
    )


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


def test_first_dial_attempt_reuses_loaded_calls_page(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "src.gv_controller.QTimer.singleShot",
        lambda ms, fn: scheduled.append((ms, fn)),
    )
    ctrl = _controller_for("+17085681794")
    ctrl._active_call = True
    ctrl._pending_dial_phone = "+17085681794"
    ctrl._dial_step_attempts = 0
    ctrl._page = _FakePage("https://voice.google.com/u/0/calls")
    ctrl._emit_log = lambda _msg: None

    ctrl._ensure_calls_page_then_dial()

    assert ctrl._page.loaded == []
    assert ctrl._page.js
    assert scheduled and scheduled[-1][0] == 700


def test_first_dial_attempt_loads_calls_page_only_when_off_voice(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "src.gv_controller.QTimer.singleShot",
        lambda ms, fn: scheduled.append((ms, fn)),
    )
    ctrl = _controller_for("+17085681794")
    ctrl._active_call = True
    ctrl._pending_dial_phone = "+17085681794"
    ctrl._dial_step_attempts = 0
    ctrl._page = _FakePage("about:blank")
    ctrl._emit_log = lambda _msg: None

    ctrl._ensure_calls_page_then_dial()

    assert ctrl._page.loaded == ["https://voice.google.com/u/0/calls"]
    assert scheduled and scheduled[-1][0] == 2500


def test_disabled_native_field_falls_back_to_direct_dial_url(monkeypatch):
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
    ctrl._native_key_attempted = True
    ctrl._dial_step_attempts = 4
    ctrl._page = _FakePage("https://voice.google.com/u/0/calls")
    ctrl._emit_log = lambda _msg: None

    ctrl._handle_retryable_dial_status("call_button_missing")

    assert ctrl._dial_url_variant == 1
    assert ctrl._page.loaded == ["https://voice.google.com/dial/+17085681794"]
    assert scheduled and scheduled[-1][0] == 2500


def test_native_keypad_status_clicks_each_digit():
    ctrl = _controller_for("+17085681794")
    ctrl.view = _FakeView()
    ctrl._native_key_attempts = 0
    ctrl._native_key_attempted = False
    ctrl._emit_log = lambda _msg: None
    ctrl._page = _FakePage("https://voice.google.com/u/0/calls")
    clicked = []
    ctrl._click_view_coords = lambda x, y: clicked.append((x, y)) or True

    assert ctrl._click_keypad_from_status(
        "keypad_needs_native_clicks|reason=disabled|input=4,5|coords=7,10,20;0,30,40;8,50,60;5,70,80;6,90,100;8,110,120;1,130,140;7,150,160;9,170,180;4,190,200"
    )
    assert clicked == [(10, 20), (30, 40), (50, 60), (70, 80), (90, 100), (110, 120), (130, 140), (150, 160), (170, 180), (190, 200), (4, 5)]


def test_js_dial_supports_click_only_mode():
    from src.gv_controller import _js_dial

    js = _js_dial("+17085681794", click_only=True)
    assert "clickOnly=true" in js
    assert "numberLooksEntered" in js


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
