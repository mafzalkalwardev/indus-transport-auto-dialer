"""
Predictive / Power Dialer — manages N simultaneous Google Voice call slots.

Each slot runs one Chrome profile (= one GV account).
When any slot reaches CONNECTED, the on_connected callback fires so the
human agent can take over that Chrome window and talk to the prospect.
Voicemail and no-answer calls are handled automatically in the background.
"""
from __future__ import annotations

import os
import queue
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

from src.browser import GoogleVoiceBrowser
from src.call_session import CallSession, CallState
from src.paths import CHROME_PROFILES_DIR
from src.phone_utils import fmt_e164, fmt_display


class SlotStatus(str, Enum):
    IDLE       = "IDLE"
    LAUNCHING  = "LAUNCHING"
    LOGIN_WAIT = "LOGIN_WAIT"
    DIALING    = "DIALING"
    RINGING    = "RINGING"
    CONNECTED  = "CONNECTED"
    VOICEMAIL  = "VOICEMAIL"
    NO_ANSWER  = "NO_ANSWER"
    FAILED     = "FAILED"
    STOPPED    = "STOPPED"


@dataclass
class SlotState:
    slot_id:       int
    profile_name:  str
    status:        SlotStatus    = SlotStatus.IDLE
    current_phone: str           = ""
    contact_name:  str           = ""
    call_start:    Optional[float] = None
    browser:       Optional[GoogleVoiceBrowser] = None
    release_event: threading.Event = field(default_factory=threading.Event)
    thread:        Optional[threading.Thread] = None

    def elapsed(self) -> str:
        if self.call_start:
            s = int(time.time() - self.call_start)
            return f"{s//60:02d}:{s%60:02d}"
        return "—"


class PredictiveDialer:
    """
    Manages N simultaneous outbound call slots.

    Callbacks (all called from worker threads — use root.after in UI):
      on_status(slot_id, SlotStatus, phone, elapsed)
      on_connected(slot_id, phone, browser)   ← agent must call release(slot_id) when done
      on_log(msg)
      on_all_done()
    """

    def __init__(
        self,
        n_slots:      int = 2,
        call_timeout: int = 60,
        cooldown_min: float = 2.0,
        cooldown_max: float = 4.0,
    ):
        self.n_slots      = n_slots
        self.call_timeout = call_timeout
        self.cooldown_min = cooldown_min
        self.cooldown_max = cooldown_max

        self.slots: list[SlotState] = []
        self._contact_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._running  = False
        self._lock     = threading.Lock()

        # Callbacks — set before calling start()
        self.on_status:    Optional[Callable] = None   # (slot_id, SlotStatus, phone, elapsed)
        self.on_connected: Optional[Callable] = None   # (slot_id, phone, browser)
        self.on_log:       Optional[Callable] = None   # (msg)
        self.on_all_done:  Optional[Callable] = None   # ()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, contacts: list[tuple[str, str]]) -> None:
        """
        contacts: list of (phone_e164, name) tuples.
        Launches all slots and starts dialing.
        """
        self._running = True
        for phone, name in contacts:
            self._contact_queue.put((phone, name))

        # Build slot state objects
        self.slots = []
        for i in range(self.n_slots):
            profile_name = f"slot_{i}"
            profile_dir  = os.path.join(CHROME_PROFILES_DIR, profile_name)
            slot = SlotState(slot_id=i, profile_name=profile_name)
            slot.browser = GoogleVoiceBrowser(profile_dir=profile_dir)
            self.slots.append(slot)

        # Launch each slot in its own thread
        for slot in self.slots:
            t = threading.Thread(
                target=self._slot_worker, args=(slot,), daemon=True)
            slot.thread = t
            t.start()

    def stop(self) -> None:
        self._running = False
        # Unblock any slots waiting for release
        for slot in self.slots:
            slot.release_event.set()
        # Drain queue
        while not self._contact_queue.empty():
            try:
                self._contact_queue.get_nowait()
            except queue.Empty:
                break

    def release(self, slot_id: int) -> None:
        """Agent calls this when finished talking on a CONNECTED slot."""
        for slot in self.slots:
            if slot.slot_id == slot_id:
                slot.release_event.set()
                break

    def is_running(self) -> bool:
        return self._running

    def get_slot_states(self) -> list[SlotState]:
        return list(self.slots)

    # ── Internal: per-slot worker thread ─────────────────────────────────────

    def _slot_worker(self, slot: SlotState) -> None:
        self._emit_log(f"[Slot {slot.slot_id}] Launching Chrome…")
        self._set_status(slot, SlotStatus.LAUNCHING, "")

        if not slot.browser.launch():
            self._emit_log(f"[Slot {slot.slot_id}] ❌ Chrome failed to launch")
            self._set_status(slot, SlotStatus.FAILED, "")
            return

        # Wait for Google Voice login (persistent profile auto-logs in)
        if not slot.browser.is_logged_in():
            self._set_status(slot, SlotStatus.LOGIN_WAIT, "")
            self._emit_log(
                f"[Slot {slot.slot_id}] ⏳ Waiting for Google login in Chrome window…"
            )
            ok = slot.browser.wait_for_manual_login(
                timeout=300,
                status_cb=lambda m: self._emit_log(f"[Slot {slot.slot_id}] {m}")
            )
            if not ok:
                self._emit_log(f"[Slot {slot.slot_id}] ❌ Login timeout")
                self._set_status(slot, SlotStatus.FAILED, "")
                slot.browser.quit()
                return

        self._emit_log(f"[Slot {slot.slot_id}] ✅ Logged in — ready")

        # Main dial loop
        while self._running:
            try:
                phone, name = self._contact_queue.get_nowait()
            except queue.Empty:
                break

            self._dial_one(slot, phone, name)

            if self._running and not self._contact_queue.empty():
                cooldown = random.uniform(self.cooldown_min, self.cooldown_max)
                self._emit_log(
                    f"[Slot {slot.slot_id}] ⏸ Cooldown {cooldown:.1f}s…"
                )
                time.sleep(cooldown)

        self._set_status(slot, SlotStatus.IDLE, "")
        slot.browser.quit()
        self._emit_log(f"[Slot {slot.slot_id}] Done — browser closed")
        self._check_all_done()

    def _dial_one(self, slot: SlotState, phone: str, name: str) -> None:
        display = fmt_display(phone[2:]) if phone.startswith("+1") and len(phone) == 12 \
            else phone
        slot.current_phone = phone
        slot.contact_name  = name
        slot.call_start    = time.time()
        slot.release_event.clear()

        session = CallSession(phone=phone, contact_name=name)

        self._emit_log(f"[Slot {slot.slot_id}] 📞 Dialing {display}…")
        self._set_status(slot, SlotStatus.DIALING, phone)

        try:
            session.transition(CallState.DIALING, "starting call")
            dialed = slot.browser.dial(phone)
        except Exception as e:
            self._emit_log(f"[Slot {slot.slot_id}] ❌ Dial error: {e}")
            self._set_status(slot, SlotStatus.FAILED, phone)
            self._log_result(slot, phone, "FAILED")
            return

        if not dialed:
            self._emit_log(f"[Slot {slot.slot_id}] ❌ Could not dial {display}")
            self._set_status(slot, SlotStatus.FAILED, phone)
            self._log_result(slot, phone, "FAILED")
            return

        self._set_status(slot, SlotStatus.RINGING, phone)
        self._emit_log(f"[Slot {slot.slot_id}] 🔔 Ringing {display}…")

        final = slot.browser.detect_call_state(
            session, timeout=self.call_timeout, poll_interval=0.75
        )

        if final == CallState.CONNECTED:
            self._on_call_connected(slot, phone, session)

        elif final == CallState.VOICEMAIL:
            self._emit_log(f"[Slot {slot.slot_id}] 📭 Voicemail — {display}")
            self._set_status(slot, SlotStatus.VOICEMAIL, phone)
            time.sleep(2)                      # brief wait for beep
            slot.browser.hangup()
            self._log_result(slot, phone, "VOICEMAIL")

        else:   # FAILED / ENDED / NO_ANSWER
            self._emit_log(f"[Slot {slot.slot_id}] 📵 No answer — {display}")
            self._set_status(slot, SlotStatus.NO_ANSWER, phone)
            slot.browser.hangup()
            self._log_result(slot, phone, "NO_ANSWER")

        slot.current_phone = ""
        slot.call_start    = None

    def _on_call_connected(self, slot: SlotState,
                            phone: str, session: CallSession) -> None:
        display = fmt_display(phone[2:]) if phone.startswith("+1") and len(phone) == 12 \
            else phone
        self._emit_log(
            f"[Slot {slot.slot_id}] 🟢 CONNECTED — {display} — bringing to front"
        )
        self._set_status(slot, SlotStatus.CONNECTED, phone)

        # Bring Chrome window to agent's screen
        slot.browser.focus_window()

        # Fire callback to UI — agent must call release() when done
        if self.on_connected:
            self.on_connected(slot.slot_id, phone, slot.browser)

        # Block this thread until agent releases the slot
        slot.release_event.wait()

        if slot.browser.is_call_active():
            slot.browser.hangup()

        dur = session.connected_duration_s() or 0
        self._emit_log(
            f"[Slot {slot.slot_id}] 📴 Call ended  "
            f"({dur:.0f}s connected) — {display}"
        )
        self._log_result(slot, phone, "ENDED", duration_s=dur)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, slot: SlotState, status: SlotStatus, phone: str) -> None:
        slot.status = status
        if self.on_status:
            try:
                self.on_status(slot.slot_id, status, phone, slot.elapsed())
            except Exception:
                pass

    def _emit_log(self, msg: str) -> None:
        if self.on_log:
            try:
                self.on_log(msg)
            except Exception:
                pass

    def _log_result(self, slot: SlotState, phone: str,
                    status: str, duration_s: float = 0.0) -> None:
        # Stored via the UI's db reference — the UI connects on_log_call callback
        if hasattr(self, "_log_call_cb") and self._log_call_cb:
            try:
                self._log_call_cb(slot.slot_id, phone,
                                   slot.contact_name, status, duration_s)
            except Exception:
                pass

    def _check_all_done(self) -> None:
        if self._contact_queue.empty():
            all_idle = all(
                s.status in (SlotStatus.IDLE, SlotStatus.STOPPED,
                              SlotStatus.FAILED)
                for s in self.slots
            )
            if all_idle and self.on_all_done:
                try:
                    self.on_all_done()
                except Exception:
                    pass
