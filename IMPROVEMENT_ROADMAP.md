# AUTO DIALER PRO - IMPROVEMENT ROADMAP & CODE FIXES

## Quick Priority Actions

### 🔴 CRITICAL (Week 1-2)

#### 1. Add Slot Watchdog (Health Check)
**File:** `src/slot_watchdog.py` (NEW)

```python
"""
Monitors slot health and auto-restarts failed Chrome instances.
Prevents zombie slots.
"""
import threading
import time
from typing import Callable, Optional

class SlotWatchdog:
    def __init__(self, check_interval: float = 5.0):
        self.check_interval = check_interval
        self._running = False
        self._checks: dict[int, SlotCheck] = {}
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
    
    def watch(self, slot_id: int, browser, restart_callback: Callable) -> None:
        """Register a slot for monitoring."""
        with self._lock:
            self._checks[slot_id] = SlotCheck(
                slot_id=slot_id,
                browser=browser,
                restart_cb=restart_callback,
                last_response=time.time()
            )
    
    def heartbeat(self, slot_id: int) -> None:
        """Call this when slot responds (dial success)."""
        with self._lock:
            if slot_id in self._checks:
                self._checks[slot_id].last_response = time.time()
    
    def start(self) -> None:
        """Start background watchdog thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
    
    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
    
    def _monitor_loop(self) -> None:
        while self._running:
            time.sleep(self.check_interval)
            with self._lock:
                for slot_id, check in list(self._checks.items()):
                    elapsed = time.time() - check.last_response
                    
                    # No response for >30s = likely dead
                    if elapsed > 30:
                        print(f"[Watchdog] Slot {slot_id} unresponsive ({elapsed:.0f}s)")
                        try:
                            check.browser.quit()
                            check.restart_cb(slot_id)
                            check.last_response = time.time()
                        except Exception as e:
                            print(f"[Watchdog] Error restarting slot {slot_id}: {e}")
                    
                    # Chrome memory check (if available)
                    try:
                        mem_mb = self._get_chrome_memory(check.browser)
                        if mem_mb > 600:  # > 600 MB = restart
                            print(f"[Watchdog] Slot {slot_id} using {mem_mb}MB, restarting")
                            check.browser.quit()
                            check.restart_cb(slot_id)
                    except Exception:
                        pass  # Can't check memory; skip
    
    def _get_chrome_memory(self, browser) -> int:
        """Get Chrome process memory in MB (Windows only)."""
        try:
            import psutil
            if not browser.driver:
                return 0
            pid = browser.driver.service.process.pid
            p = psutil.Process(pid)
            return int(p.memory_info().rss / 1024 / 1024)
        except Exception:
            return 0

@dataclass
class SlotCheck:
    slot_id: int
    browser: 'GoogleVoiceBrowser'
    restart_cb: Callable
    last_response: float
```

**Integration in main:**
```python
# In autodialer_gui.py, add to MainWindow.__init__:
self.watchdog = SlotWatchdog(check_interval=5.0)
self.watchdog.start()

# In _init_controllers:
for ctrl in self._controllers:
    self.watchdog.watch(
        slot_id=ctrl.slot_id,
        browser=ctrl._page,  # or actual browser object
        restart_callback=self._restart_slot
    )

# In _assign_pending_calls (when dial succeeds):
self.watchdog.heartbeat(ctrl.slot_id)

# Add restart method:
def _restart_slot(self, slot_id: int):
    self._log(f"[System] Restarting slot {slot_id}...")
    # Reinitialize this slot
    ...
```

---

#### 2. Add Retry Logic with Exponential Backoff
**File:** `src/predictive_dialer.py` (MODIFY `_dial_one` method)

```python
def _dial_one(self, slot: SlotState, phone: str, name: str) -> None:
    # ... existing setup ...
    
    MAX_RETRIES = 3
    
    for attempt in range(MAX_RETRIES):
        try:
            self._emit_log(f"[Slot {slot.slot_id}] 📞 Dialing {display}… "
                          f"(attempt {attempt + 1}/{MAX_RETRIES})")
            
            dialed = slot.browser.dial(phone)
            
            if not dialed:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt  # 2s, 4s, 8s
                    self._emit_log(
                        f"[Slot {slot.slot_id}] ⏳ Dial failed, "
                        f"retry in {wait}s…"
                    )
                    time.sleep(wait)
                    continue
                else:
                    raise Exception("All dial attempts exhausted")
            
            # Dial succeeded; proceed with state detection
            self._set_status(slot, SlotStatus.RINGING, phone)
            final = slot.browser.detect_call_state(
                session, timeout=self.call_timeout, poll_interval=0.75
            )
            # ... rest of logic ...
            return
        
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = 2 ** attempt
                self._emit_log(f"[Slot {slot.slot_id}] ❌ Error: {e}, "
                              f"retrying in {wait}s…")
                time.sleep(wait)
            else:
                self._emit_log(f"[Slot {slot.slot_id}] ❌ Failed after "
                              f"{MAX_RETRIES} attempts: {e}")
                self._set_status(slot, SlotStatus.FAILED, phone)
                self._log_result(slot, phone, "FAILED_RETRIES_EXHAUSTED")
                return
```

---

#### 3. Add DOM Selector Screenshot Fallback
**File:** `src/browser.py` (ADD method to GoogleVoiceBrowser)

```python
def _detect_state_from_screenshot(self) -> str:
    """
    Fallback state detection using screenshot + OCR.
    Called when DOM selectors fail.
    """
    try:
        import pytesseract
        from PIL import Image
        import io
    except ImportError:
        return "UNKNOWN"
    
    try:
        # Capture screenshot
        screenshot_bytes = self.driver.get_screenshot_as_png()
        img = Image.open(io.BytesIO(screenshot_bytes))
        
        # Extract text via OCR
        text = pytesseract.image_to_string(img).lower()
        
        # Simple heuristics
        if "call ended" in text or "missed call" in text:
            return CallState.ENDED
        if "voicemail" in text or "leave a message" in text:
            return CallState.VOICEMAIL
        if "ringing" in text or "calling" in text:
            return CallState.RINGING
        if "mute" in text or "hold" in text:  # Answered controls visible
            return CallState.CONNECTED
        
        # Look for call timer (e.g., "0:45" format)
        import re
        if re.search(r'\b\d{1,2}:\d{2}\b', text):
            return CallState.CONNECTED
        
        return CallState.UNKNOWN
    
    except Exception as e:
        print(f"Screenshot fallback error: {e}")
        return "UNKNOWN"

def detect_call_state(self, session, timeout=90.0, poll_interval=0.75):
    """MODIFY: Add fallback to screenshot if DOM detection fails."""
    start = time.time()
    
    while time.time() - start < timeout:
        try:
            # Try existing DOM-based detection
            state = self._detect_call_state_from_dom()
            if state != "UNKNOWN":
                return state
        except Exception:
            pass
        
        # Fallback to screenshot
        state = self._detect_state_from_screenshot()
        if state != "UNKNOWN":
            return state
        
        time.sleep(poll_interval)
    
    return CallState.NO_ANSWER
```

**Install OCR support:**
```bash
pip install pytesseract pillow
# Also requires Tesseract binary: https://github.com/UB-Mannheim/tesseract/wiki
```

---

### 🟠 HIGH PRIORITY (Week 2-3)

#### 4. Add 2FA/TOTP Support
**File:** `src/gv_accounts.py` (MODIFY `load_accounts`)

```python
def load_accounts() -> list[dict[str, Any]]:
    # ... existing code ...
    accounts.append({
        "name": name,
        "email": email,
        "password": str(raw.get("password", "")),
        "profile": profile,
        "notes": str(raw.get("notes", "")).strip(),
        "totp_secret": str(raw.get("totp_secret", "")),  # NEW
        "use_2fa": bool(raw.get("use_2fa", False)),      # NEW
    })
    # ... rest ...
```

**File:** `src/browser.py` (ADD method)

```python
def _complete_totp_challenge(self, totp_secret: str, max_attempts: int = 5) -> bool:
    """
    Auto-complete TOTP 2FA challenge.
    Requires: pip install pyotp
    """
    try:
        import pyotp
    except ImportError:
        print("pyotp not installed; skipping TOTP")
        return False
    
    totp = pyotp.TOTP(totp_secret)
    
    for attempt in range(max_attempts):
        try:
            # Wait for TOTP input field
            wait = WebDriverWait(self.driver, 10)
            totp_input = wait.until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    'input[inputmode="numeric"]'
                ))
            )
            
            # Enter current TOTP code
            code = totp.now()
            totp_input.send_keys(code)
            totp_input.send_keys(Keys.RETURN)
            
            # Wait for next page (login success or another challenge)
            time.sleep(2)
            return True
        
        except (TimeoutException, NoSuchElementException):
            if attempt < max_attempts - 1:
                # TOTP expired; wait for next 30s window
                time.sleep(30)
            else:
                return False
    
    return False
```

---

#### 5. Add Call Recording (Audio Capture)
**File:** `src/call_recorder.py` (NEW)

```python
"""
Capture and save Google Voice call audio.
Uses Chrome DevTools Protocol.
"""
import json
import subprocess
import threading
from typing import Optional

class CallRecorder:
    def __init__(self, output_dir: str = "recordings"):
        self.output_dir = output_dir
        import os
        os.makedirs(output_dir, exist_ok=True)
    
    def start_recording(self, browser_driver, phone: str) -> str:
        """
        Start recording Chrome audio via DevTools.
        Returns session ID for later retrieval.
        """
        session_id = f"{phone}_{int(time.time())}"
        
        # Chrome DevTools Protocol command to enable audio capture
        try:
            # This requires Chrome to be launched with audio capture enabled
            # and WebRTC audio to flow through the browser
            self._setup_audio_capture(browser_driver, session_id)
        except Exception as e:
            print(f"Failed to setup recording: {e}")
        
        return session_id
    
    def _setup_audio_capture(self, driver, session_id: str):
        """
        Setup Chrome DevTools Protocol for audio capture.
        Requires: pip install chrome-remote-debugging-client
        """
        try:
            # Access Chrome DevTools endpoint
            endpoints = driver.execute_script(
                "return JSON.stringify(performance.timing)"
            )
            # Complex; simplify for MVP
        except Exception as e:
            print(f"DevTools setup error: {e}")
    
    def stop_recording(self, session_id: str) -> Optional[str]:
        """Stop recording and save file."""
        try:
            # Save recorded audio
            output_file = os.path.join(
                self.output_dir,
                f"{session_id}.wav"
            )
            return output_file
        except Exception as e:
            print(f"Failed to save recording: {e}")
        return None
```

**Better alternative: System audio capture**
```python
import pyaudio
import wave

class SystemAudioRecorder:
    def __init__(self, output_dir: str = "recordings"):
        self.output_dir = output_dir
        self.recording = False
        self.frames = []
    
    def start(self, phone: str) -> str:
        """Start system audio recording."""
        self.frames = []
        self.recording = True
        self.phone = phone
        
        t = threading.Thread(target=self._record_loop, daemon=True)
        t.start()
        return f"{phone}_{int(time.time())}"
    
    def _record_loop(self):
        """Capture from system audio (microphone/speakers)."""
        try:
            p = pyaudio.PyAudio()
            stream = p.open(
                format=pyaudio.paFloat32,
                channels=2,  # Stereo (speaker + mic)
                rate=16000,
                input=True,
                input_device_index=None  # Use default loopback
            )
            
            while self.recording:
                data = stream.read(1024)
                self.frames.append(data)
            
            stream.stop_stream()
            stream.close()
            p.terminate()
        except Exception as e:
            print(f"Recording error: {e}")
    
    def stop(self, session_id: str) -> Optional[str]:
        """Stop and save recording."""
        self.recording = False
        
        if not self.frames:
            return None
        
        try:
            output_file = os.path.join(
                self.output_dir,
                f"{session_id}.wav"
            )
            
            p = pyaudio.PyAudio()
            with wave.open(output_file, 'wb') as wf:
                wf.setnchannels(2)
                wf.setsampwidth(p.get_sample_size(pyaudio.paFloat32))
                wf.setframerate(16000)
                wf.writeframes(b''.join(self.frames))
            
            print(f"Recording saved: {output_file}")
            return output_file
        except Exception as e:
            print(f"Failed to save recording: {e}")
        return None
```

**Installation:**
```bash
pip install pyaudio
```

---

### 🟡 MEDIUM PRIORITY (Week 3-4)

#### 6. Add Dead-Letter Queue for Retries
**File:** `src/dead_letter_queue.py` (NEW)

```python
"""
Store failed calls for retry later.
"""
import json
import os
from datetime import datetime, timedelta

class DeadLetterQueue:
    def __init__(self, dlq_file: str = "dlq.json"):
        self.dlq_file = dlq_file
    
    def add(self, phone: str, name: str, reason: str, retry_at: datetime = None):
        """Add failed call to queue."""
        if retry_at is None:
            retry_at = datetime.now() + timedelta(hours=1)
        
        entry = {
            "phone": phone,
            "name": name,
            "reason": reason,
            "failed_at": datetime.now().isoformat(),
            "retry_at": retry_at.isoformat(),
            "attempts": 0
        }
        
        queue = self._load()
        queue.append(entry)
        self._save(queue)
    
    def get_ready(self) -> list[dict]:
        """Get all calls ready to retry."""
        queue = self._load()
        now = datetime.now()
        ready = [
            e for e in queue
            if datetime.fromisoformat(e["retry_at"]) <= now
        ]
        return ready
    
    def mark_retried(self, phone: str):
        """Remove from DLQ after successful retry."""
        queue = self._load()
        queue = [e for e in queue if e["phone"] != phone]
        self._save(queue)
    
    def _load(self) -> list[dict]:
        if not os.path.exists(self.dlq_file):
            return []
        try:
            with open(self.dlq_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    
    def _save(self, queue: list[dict]):
        with open(self.dlq_file, 'w') as f:
            json.dump(queue, f, indent=2)
```

**Integration in predictive_dialer.py:**
```python
from src.dead_letter_queue import DeadLetterQueue

class PredictiveDialer:
    def __init__(self, ...):
        # ... existing ...
        self.dlq = DeadLetterQueue()
    
    def _dial_one(self, slot, phone, name):
        # ... after MAX_RETRIES exhausted ...
        if attempt >= MAX_RETRIES - 1:
            # Store in DLQ for later retry
            self.dlq.add(
                phone=phone,
                name=name,
                reason="Max retries exceeded",
                retry_at=datetime.now() + timedelta(hours=2)
            )
    
    def retry_failed(self):
        """Call this periodically to retry failed numbers."""
        ready = self.dlq.get_ready()
        for entry in ready:
            self._contact_queue.put((entry["phone"], entry["name"]))
            self.dlq.mark_retried(entry["phone"])
```

---

#### 7. Add Monitoring & Error Logging
**File:** `src/monitoring.py` (NEW)

```python
"""
Error logging and metrics collection.
"""
import json
import logging
from datetime import datetime
from collections import defaultdict

class DialerMetrics:
    def __init__(self, log_file: str = "metrics.log"):
        self.log_file = log_file
        self.stats = defaultdict(int)
        
        # Setup logging
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
    
    def log_error(self, slot_id: int, error: str):
        """Log error with context."""
        logging.error(f"[Slot {slot_id}] {error}")
        self.stats['errors'] += 1
    
    def log_call_result(self, phone: str, status: str, duration_s: float):
        """Log call outcome."""
        logging.info(f"{phone} -> {status} ({duration_s:.0f}s)")
        self.stats[f"status_{status}"] += 1
        self.stats['total_calls'] += 1
    
    def get_stats(self) -> dict:
        """Get current metrics."""
        total = self.stats.get('total_calls', 0)
        connected = self.stats.get('status_CONNECTED', 0)
        voicemail = self.stats.get('status_VOICEMAIL', 0)
        no_answer = self.stats.get('status_NO_ANSWER', 0)
        failed = self.stats.get('status_FAILED', 0)
        
        success_rate = (connected / total * 100) if total > 0 else 0
        
        return {
            "total_calls": total,
            "connected": connected,
            "voicemail": voicemail,
            "no_answer": no_answer,
            "failed": failed,
            "success_rate_%": success_rate,
            "errors": self.stats.get('errors', 0),
        }
    
    def alert_if_needed(self, threshold_error_rate: float = 0.1):
        """Alert if error rate exceeds threshold."""
        stats = self.get_stats()
        if stats['total_calls'] > 0:
            error_rate = stats['errors'] / stats['total_calls']
            if error_rate > threshold_error_rate:
                logging.warning(
                    f"⚠️ High error rate: {error_rate:.1%}"
                )
                return True
        return False
```

---

## 🚀 DEPLOYMENT CHECKLIST

### Before Production Launch

- [ ] Install all dependencies: `pip install -r requirements_enhanced.txt`
- [ ] Run watchdog tests: `pytest tests/test_watchdog.py`
- [ ] Run retry logic tests: `pytest tests/test_retry.py`
- [ ] Run 2FA tests with real GV account
- [ ] Test call recording with 5+ test calls
- [ ] Load test: 1000 numbers, 8 slots, 2 hours → measure CPU, RAM, errors
- [ ] Backup database and Chrome profiles
- [ ] Enable error logging
- [ ] Configure monitoring alerts (email on high error rate)
- [ ] Document runbook for common issues

### Enhanced requirements.txt

```
PyQt6>=6.7.0
PyQt6-WebEngine>=6.7.0
pandas>=1.5.0
openpyxl>=3.0.0
Pillow>=9.0.0
pyperclip>=1.8.0
pyinstaller>=6.0.0
selenium>=4.0.0
pyotp>=2.8.0
pytesseract>=0.3.10
pyaudio>=0.2.13
psutil>=5.9.0
chrome-remote-debugging-client>=0.0.1
```

---

## Summary: 4-Week Roadmap

| Week | Priority | Tasks |
|------|----------|-------|
| **1** | 🔴 Critical | Watchdog, basic retry, screenshot fallback |
| **2** | 🟠 High | 2FA support, call recording (system audio), error logging |
| **3** | 🟡 Medium | Dead-letter queue, monitoring, load testing |
| **4** | 🟢 Polish | Documentation, runbook, production deployment, final testing |

---

**Effort Estimate:** 60-80 developer-hours  
**Team:** 1-2 engineers, 1 QA  
**Timeline:** 4-6 weeks with part-time work
