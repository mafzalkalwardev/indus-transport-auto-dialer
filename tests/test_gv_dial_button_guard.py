from PyQt6.QtWidgets import QApplication, QWidget

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
