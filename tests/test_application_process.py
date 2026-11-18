"""Real worker and PTY/VisiData; the editor transport is an explicit test fixture."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time

import pytest

from jusi.application.ports import PluginOperationError, PluginWorkerError, PluginWorkerSpec
from jusi.infrastructure.plugin_worker import FreshProcessPluginWorkerFactory

from jusi_web.store import Store


def wait_until(predicate, output, process, timeout=8, tick=lambda: None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        tick()
        if predicate():
            return
        assert process.poll() is None, bytes(output).decode(errors="replace")
        time.sleep(0.02)
    pytest.fail("Timed out waiting for application: " + bytes(output).decode(errors="replace")[-6000:])


def test_real_worker_and_visidata_followups(tmp_path, monkeypatch):
    # This fixture also works before the generic managed-URL extension is
    # applied. It does not claim to exercise frontend projection ownership.
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    log = tmp_path / "editor.jsonl"
    (fixture / "sitecustomize.py").write_text("""
import json, os
from jusi import editor_client
def deliver(value):
    with open(os.environ['WEB_TEST_LOG'], 'a') as stream:
        stream.write(json.dumps(value) + '\\n')
def close_url(*, slot):
    deliver({'action': 'close', 'slot': slot})
def open_url(url, *, slot=None):
    deliver({'action': 'open', 'url': url, 'slot': slot})
editor_client.close_url = close_url
editor_client.open_url = open_url
""")
    monkeypatch.setenv("PYTHONPATH", str(fixture))
    monkeypatch.setenv("WEB_TEST_LOG", str(log))
    # Tests must not load or write the user's VisiData configuration.
    home = tmp_path / "home"
    home.mkdir()
    for variable in ["HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"]:
        monkeypatch.setenv(variable, str(home))
    monkeypatch.setenv("VD_DIR", str(home / "vd"))
    store = Store(tmp_path / "history.db")
    store.rename("https://docs.test", "Python docs")
    store.rename("https://packages.test", "Python packages")

    spec = PluginWorkerSpec(
        plugin_worker_id="pwrk_web", runtime_id="runtime_web", plugin_id="jusi_web", family_id="web",
        client_id="client_web", execution_id="execution_web", entry_point="jusi_web.worker:create_worker")
    worker = FreshProcessPluginWorkerFactory().start(spec, timeout=5)
    process = None
    master = slave = None
    output = bytearray()
    try:
        launch = worker.request("execute", {"body": "", "config": {"database": str(store.path),
            "api_key_env": "JUSI_WEB_NONEXISTENT_TEST_KEY"}}, trace_id="trace_web_start", timeout=5)
        assert len(launch.core_requests) == 1
        surface = launch.core_requests[0]
        payload_path = Path(surface.argv[3])
        runtime_directory = payload_path.parent
        assert payload_path.stat().st_mode & 0o777 == 0o600
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 130, 0, 0))
        environment = {**os.environ, **surface.environment_overrides}
        process = subprocess.Popen(surface.argv, stdin=slave, stdout=slave, stderr=slave,
                                   env=environment, start_new_session=True)
        os.close(slave)
        slave = None
        os.set_blocking(master, False)

        def drain():
            while select.select([master], [], [], 0)[0]:
                try:
                    part = os.read(master, 65536)
                except OSError:
                    break
                if not part:
                    break
                output.extend(part)

        def visible(text):
            drain()
            return text.encode() in output

        def events():
            drain()
            return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

        wait_until(lambda: visible("Python docs"), output, process)
        # Exercise actual VisiData cell editing and immediate persistence.
        os.write(master, b"e\x01\x0bReference\r")
        wait_until(lambda: store.name("https://docs.test") == "Reference", output, process, tick=drain)
        os.write(master, b"U")
        wait_until(lambda: store.name("https://docs.test") == "Python docs", output, process, tick=drain)
        os.write(master, b"R")
        wait_until(lambda: store.name("https://docs.test") == "Reference", output, process, tick=drain)
        # VisiData Enter drills into the current row without ending the app.
        os.write(master, b"\r")
        wait_until(lambda: any(e.get("url") == "https://docs.test" for e in events()), output, process)
        assert process.poll() is None

        result = worker.request("followup", {"body": "Python"}, trace_id="trace_subset", timeout=8)
        assert result.result["kind"] == "open" # only the packages bookmark still matches
        assert events()[-2:] == [{"action": "close", "slot": "web"},
                                {"action": "open", "url": "https://packages.test", "slot": "web"}]
        worker.request("followup", {"body": ""}, trace_id="trace_bookmarks", timeout=8)
        assert events()[-1]["action"] == "close"
        with pytest.raises(PluginOperationError):
            worker.request("followup", {"body": "unmatched cheese request"}, trace_id="trace_search_error", timeout=8)
        # Recoverable error retains both the exact worker process and PTY app.
        original_pid = worker.pid
        response = worker.request("followup", {"body": "https://next.test"}, trace_id="trace_recovery", timeout=8)
        assert response.result["kind"] == "open"
        assert worker.pid == original_pid and process.poll() is None
        # Missing application is fatal, rather than a recoverable empty result.
        process.kill()
        process.wait(timeout=5)
        with pytest.raises(PluginWorkerError):
            worker.request("followup", {"body": ""}, trace_id="trace_dead_application", timeout=8)
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        for fd in [master, slave]:
            if fd is not None:
                os.close(fd)
        worker.stop(trace_id="trace_web_cleanup", timeout=5)
    assert not runtime_directory.exists()
