from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

from jusi.plugin_api import OperationRejected, WorkerResult, copy_text, open_text, open_url, terminal_surface

from .config import ConfigurationError, Settings
from .control import exchange
from .routing import followup_body, is_url


class WebWorker:
    def __init__(self, context):
        self.context = context
        self.directory = None
        self.socket_path = None

    def handle(self, operation, payload):
        if operation == "execute":
            if self.directory is not None:
                raise OperationRejected("Web client is already initialized", reason="conflict")
            config = payload.get("config", {})
            if not isinstance(config, dict):
                raise OperationRejected("Web configuration must be a table", reason="invalid_request")
            try:
                Settings.from_dict(config)
            except ConfigurationError as exc:
                raise OperationRejected(str(exc), reason="invalid_request") from exc
            from jusi import editor_client
            if not hasattr(editor_client, "close_url"):
                raise OperationRejected("Jusi needs managed URL actions (open_url slot and close_url) for %%web", reason="unsupported")
            self.directory = Path(tempfile.mkdtemp(prefix="jusi-web-"))
            self.directory.chmod(0o700)
            self.socket_path = self.directory / "control.sock"
            path = self.directory / "launch.json"
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump({"body": str(payload.get("body", "")), "config": config}, stream)
                return WorkerResult({"accepted": True}, (terminal_surface(
                    "web_terminal", (sys.executable, "-m", "jusi_web.application", str(path), str(self.socket_path)),
                    environment_overrides={"TERM": os.environ.get("JUSI_WEB_TERM", "xterm-256color")}, signal=True,
                ),))
            except BaseException:
                self.close()
                raise
        if operation == "followup":
            try:
                return WorkerResult(self.request({"type": "followup", "body": followup_body(str(payload.get("body", "")))}))
            except OperationRejected:
                raise
            except BaseException:
                self.close()
                raise
        if operation == "editor_action":
            selection = payload.get("selection", {})
            text = selection.get("text") if isinstance(selection, dict) else None
            if not isinstance(text, str):
                raise OperationRejected("Selection requires text", reason="invalid_request")
            if payload["action"] == "copy":
                return copy_text(text)
            if payload["action"] == "open":
                return open_text(text, name="web-selection.txt")
            if payload["action"] == "open_url" and is_url(text):
                return open_url(text, slot="web")
        raise OperationRejected(f"Unsupported web operation: {operation}", reason="unsupported")

    def request(self, request):
        if self.directory is None:
            raise OperationRejected("Web client is not initialized", reason="conflict")
        deadline = time.monotonic() + 5
        while True:
            try:
                response = exchange(self.socket_path, request)
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if time.monotonic() >= deadline:
                    # Application loss is fatal, not a recoverable search error.
                    raise RuntimeError("jusi-web application is unavailable")
                time.sleep(0.02)
        if not response.get("ok"):
            if response.get("fatal"):
                raise RuntimeError(response.get("error", "jusi-web application failed"))
            raise OperationRejected(response.get("error", "Web request failed"))
        return response

    def close(self):
        if self.directory is not None:
            shutil.rmtree(self.directory, ignore_errors=True)
        self.directory = self.socket_path = None


def create_worker(context):
    return WebWorker(context)
