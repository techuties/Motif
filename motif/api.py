"""Local HTTP control surface so other programs can trigger Motif."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import urlparse

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7842
_MAX_BODY = 1_000_000


def _origin_allowed(origin: str, host: str, port: int) -> bool:
    """Allow non-browser clients (no Origin) and same-host browser pages only."""
    origin = origin.strip().rstrip("/")
    if not origin:
        return True
    allowed = {
        f"http://{host}:{port}",
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
    }
    return origin in allowed


class MotifAPI:
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        handlers: dict[str, Callable[..., Any]] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.handlers = handlers or {}
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._server is not None

    def start(self) -> None:
        if self._server:
            return
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def _json(self, code: int, payload: Any) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _csrf_ok(self) -> bool:
                return _origin_allowed(self.headers.get("Origin") or "", api.host, api.port)

            def _body(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0:
                    return {}
                if length > _MAX_BODY:
                    raise ValueError("request body too large")
                raw = self.rfile.read(length)
                if not raw:
                    return {}
                data = json.loads(raw.decode("utf-8"))
                return data if isinstance(data, dict) else {}

            def do_GET(self) -> None:  # noqa: N802
                if not self._csrf_ok():
                    self._json(403, {"error": "origin not allowed"})
                    return
                self._dispatch("GET", urlparse(self.path).path, {})

            def do_POST(self) -> None:  # noqa: N802
                if not self._csrf_ok():
                    self._json(403, {"error": "origin not allowed"})
                    return
                try:
                    body = self._body()
                except (ValueError, json.JSONDecodeError) as exc:
                    self._json(400, {"error": str(exc)})
                    return
                self._dispatch("POST", urlparse(self.path).path, body)

            def _dispatch(self, method: str, path: str, body: dict[str, Any]) -> None:
                key = f"{method} {path}"
                fn = api.handlers.get(key)
                if fn is None:
                    self._json(404, {"error": f"unknown route {key}"})
                    return
                try:
                    result = fn(body)
                    self._json(200, result if result is not None else {"ok": True})
                except Exception as exc:  # noqa: BLE001
                    self._json(400, {"error": str(exc)})

        class Server(ThreadingHTTPServer):
            allow_reuse_address = True

        self._server = Server((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None


class MotifClient:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        self.base = f"http://{host}:{port}"

    def _call(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ConnectionError(f"Motif is not reachable at {self.base}") from exc

    def health(self) -> dict[str, Any]:
        return self._call("GET", "/health")

    def status(self) -> dict[str, Any]:
        return self._call("GET", "/status")

    def play(self, path: str | None = None, loops: int | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if path:
            body["path"] = path
        if loops is not None:
            body["loops"] = loops
        return self._call("POST", "/play", body)

    def stop(self) -> dict[str, Any]:
        return self._call("POST", "/stop", {})

    def record(self) -> dict[str, Any]:
        return self._call("POST", "/record", {})

    def script(self) -> dict[str, Any]:
        return self._call("GET", "/script")

    def load(self, path: str) -> dict[str, Any]:
        return self._call("POST", "/load", {"path": path})
