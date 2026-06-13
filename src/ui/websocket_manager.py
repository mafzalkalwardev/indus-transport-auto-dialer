"""Optional WebSocket broadcast for supervisor dashboards."""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from PyQt6.QtCore import QObject, QThread, pyqtSignal


class WebSocketServerThread(QThread):
    """Background thread hosting a minimal websockets broadcast server."""

    client_count_changed = pyqtSignal(int)
    server_error = pyqtSignal(str)

    def __init__(self, host: str = "127.0.0.1", port: int = 8765, parent: QObject | None = None):
        super().__init__(parent)
        self.host = host
        self.port = int(port)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._clients: set[Any] = set()
        self._pending: list[str] = []
        self._stop = threading.Event()

    def run(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception as exc:
            self.server_error.emit(str(exc))

    async def _serve(self) -> None:
        try:
            import websockets  # type: ignore
        except Exception as exc:
            self.server_error.emit(f"websockets unavailable: {exc}")
            return

        async def handler(ws):
            self._clients.add(ws)
            self.client_count_changed.emit(len(self._clients))
            try:
                async for _ in ws:
                    pass
            finally:
                self._clients.discard(ws)
                self.client_count_changed.emit(len(self._clients))

        async with websockets.serve(handler, self.host, self.port):
            while not self._stop.is_set():
                if self._pending:
                    payload = self._pending.pop(0)
                    dead = []
                    for client in list(self._clients):
                        try:
                            await client.send(payload)
                        except Exception:
                            dead.append(client)
                    for client in dead:
                        self._clients.discard(client)
                await asyncio.sleep(0.05)

    def broadcast(self, event: str, payload: dict[str, Any]) -> None:
        message = json.dumps({"event": event, **payload}, default=str)
        self._pending.append(message)

    def stop_server(self) -> None:
        self._stop.set()
        self.wait(2000)
