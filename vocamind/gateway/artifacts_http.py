"""任务文档 HTTP 只读服务。"""
from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import PurePosixPath
from typing import Optional
from urllib.parse import unquote, urlparse

from vocamind.tasks.artifacts import get_artifact_registry

logger = logging.getLogger(__name__)

_CONTENT_TYPES = {
    ".md": "text/markdown; charset=utf-8",
    ".markdown": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
}


class _ArtifactsHandler(BaseHTTPRequestHandler):
    server_version = "VocaMindArtifacts/1.0"

    def log_message(self, fmt: str, *args) -> None:
        logger.debug("artifacts %s - " + fmt, self.address_string(), *args)

    def _send_cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        prefix = "/api/artifacts/"
        if not parsed.path.startswith(prefix):
            self.send_error(404, "Not Found")
            return

        remainder = parsed.path[len(prefix) :]
        parts = remainder.split("/", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            self.send_error(400, "Bad Request")
            return

        task_id = parts[0]
        rel_path = unquote(parts[1])
        if PurePosixPath(rel_path).as_posix() in (".", "..") or ".." in PurePosixPath(rel_path).parts:
            self.send_error(400, "Bad Request")
            return

        registry = get_artifact_registry()
        try:
            fp = registry.resolve_file(task_id, rel_path)
            body = fp.read_bytes()
        except PermissionError:
            self.send_error(403, "Forbidden")
            return
        except FileNotFoundError:
            self.send_error(404, "Not Found")
            return
        except Exception:
            logger.exception("读取文档失败: %s/%s", task_id, rel_path)
            self.send_error(500, "Internal Server Error")
            return

        suffix = fp.suffix.lower()
        content_type = _CONTENT_TYPES.get(suffix, "text/plain; charset=utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._send_cors()
        self.end_headers()
        self.wfile.write(body)


class ArtifactsHttpServer:
    """在后台线程提供文档下载。"""

    def __init__(self, host: str, port: int, stop_event: threading.Event) -> None:
        self.host = host
        self.port = port
        self.stop_event = stop_event
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._httpd = ThreadingHTTPServer((self.host, self.port), _ArtifactsHandler)
        self._thread = threading.Thread(target=self._serve, name="artifacts-http", daemon=True)
        self._thread.start()
        logger.info("文档 HTTP 服务启动于 http://%s:%s", self.host, self.port)

    def _serve(self) -> None:
        assert self._httpd is not None
        self._httpd.timeout = 0.5
        while not self.stop_event.is_set():
            self._httpd.handle_request()
        self._httpd.server_close()
