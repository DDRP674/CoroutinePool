"""Minimal local portrait display driven by RobotState.State."""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


def publish_robot_state(robot_state, display) -> tuple[float, str]:
    """Publish one consistent visualization update from a RobotState-like object."""
    state = robot_state.state_get()
    image = robot_state.state_tachie_get()
    if not image:
        raise ValueError("RobotState did not select a portrait")
    display.publish(state, image)
    return state, image


class manager:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        *,
        open_browser: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.open_browser = open_browser
        self.root = Path(__file__).resolve().parent
        self.assets = self.root / "assets"

        self._lock = threading.Lock()
        self._state = 0.0
        self._image = "normal"
        self._version = 0
        self._server: Optional[ThreadingHTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None

    def publish(self, state: float, image: str) -> None:
        if not isinstance(state, (int, float)):
            raise TypeError("state must be a number")
        if not isinstance(image, str) or not image:
            raise ValueError("image must be a non-empty filename stem")
        if Path(image).name != image or not (self.assets / f"{image}.png").is_file():
            raise ValueError(f"portrait does not exist: {image}")

        state = float(state)
        with self._lock:
            if state == self._state and image == self._image:
                return
            self._state = state
            self._image = image
            self._version += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "image": self._image,
                "version": self._version,
            }

    def _handler_type(self):
        display = self
        root = str(self.root)

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=root, **kwargs)

            def do_GET(self) -> None:
                if urlparse(self.path).path == "/api/state":
                    body = json.dumps(display.snapshot()).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                super().do_GET()

            def log_message(self, format: str, *args) -> None:
                pass

        return Handler

    @property
    def url(self) -> str:
        port = self._server.server_port if self._server is not None else self.port
        host = "127.0.0.1" if self.host in ("0.0.0.0", "::") else self.host
        return f"http://{host}:{port}"

    def start(self) -> None:
        if self._server is not None:
            return
        self._server = ThreadingHTTPServer((self.host, self.port), self._handler_type())
        self._server.daemon_threads = True
        self._server_thread = threading.Thread(
            target=self._server.serve_forever,
            name="Display-server",
            daemon=True,
        )
        self._server_thread.start()
        if self.open_browser:
            webbrowser.open(self.url)

    def stop(self) -> None:
        server = self._server
        thread = self._server_thread
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._server = None
        self._server_thread = None

    close = stop


DisplayManager = manager
