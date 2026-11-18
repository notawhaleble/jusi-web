"""Private target-side application IPC, independent of Jusi control transport."""
from __future__ import annotations

import json
import socket
import socketserver
import threading


def exchange(path, request):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(1)
        connection.connect(str(path))
        # Searches and editor acknowledgments have their own lifetime. Do not
        # turn a healthy long-running operation into a broken IPC connection.
        connection.settimeout(None)
        with connection.makefile("rwb") as stream:
            stream.write(json.dumps(request).encode("utf-8") + b"\n")
            stream.flush()
            raw = stream.readline()
    if not raw:
        raise ConnectionError("jusi-web application closed its control connection")
    response = json.loads(raw)
    if not isinstance(response, dict):
        raise ValueError("Invalid jusi-web application response")
    return response


class ControlServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def __init__(self, path, dispatch):
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                try:
                    request = json.loads(self.rfile.readline())
                    result = dispatch(request)
                except Exception as exc:
                    # Unexpected failures are not classified as recoverable.
                    result = {"ok": False, "fatal": True, "error": f"{type(exc).__name__}: {exc}"}
                self.wfile.write(json.dumps(result).encode("utf-8") + b"\n")

        super().__init__(str(path), Handler)
        self.thread = threading.Thread(target=self.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.shutdown()
        self.server_close()
        self.thread.join(timeout=2)
