"""QtWebEngine process flags that must be set before WebEngine imports."""
from __future__ import annotations

import os


def configure_webengine_environment() -> None:
    """Apply stable Chromium flags before QtWebEngine is imported."""
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    for flag in (
        "--disable-gpu",
        "--disable-gpu-compositing",
        "--disable-software-rasterizer",
        "--disable-features=VizDisplayCompositor",
        "--autoplay-policy=no-user-gesture-required",
        "--use-fake-ui-for-media-stream",
        "--enable-media-stream",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
    ):
        if flag not in flags:
            flags = f"{flags} {flag}".strip()
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = flags
    os.environ.setdefault(
        "QT_LOGGING_RULES",
        "*.debug=false;qt.webenginecontext*=false",
    )
