from src.gv_controller import GVController, _js_retry_start_call


def test_js_retry_start_call_includes_phone():
    js = _js_retry_start_call("+19097202727")
    assert "9097202727" in js
    assert "retry_clicked" in js or "retry_no_button" in js


def test_retry_start_call_requires_phone():
    ctrl = GVController.__new__(GVController)
    ctrl._page_alive = lambda: True
    ctrl._pending_dial_phone = ""
    ctrl._current_call_phone = ""
    ctrl._active_call = False
    ctrl._emit_log = lambda _m: None
    ctrl.retry_start_call()
    assert ctrl._active_call is False
