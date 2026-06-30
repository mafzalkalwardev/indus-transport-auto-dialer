"""Start the local AMD FastAPI server (faster-whisper + classifier + optional Ollama)."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.detection.amd_fastapi_server import main

if __name__ == "__main__":
    main()
