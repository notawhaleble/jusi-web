import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import shutil
import subprocess
import sys
import threading
import time

import pytest

from jusi_web.store import Store


def test_real_neovim_lifecycle(tmp_path):
    from jusi import editor_client

    if not shutil.which("nvim"):
        pytest.skip("Neovim is not installed")
    if not hasattr(editor_client, "close_url"):
        pytest.skip("Jusi managed-URL extension is not installed; use PYTHONPATH with a patched Jusi checkout")
    source = Path(os.environ.get("JUSI_SOURCE_ROOT", Path(__file__).resolve().parents[2] / "jusi")).resolve()
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(request)
            # Let VisiData reach its normal idle threshold before publishing
            # results. No terminal input may be needed to reveal them.
            time.sleep(1.5)
            self.send_response(429 if request["input"] == "break search" else 200)
            self.end_headers()
            self.wfile.write(json.dumps({"status": "completed", "output": [{"type": "search_results", "results": [
                {"url": "https://citation-a.test", "title": "Result A"},
                {"url": "https://citation-b.test", "title": "Result B"},
            ]}]}).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    database = tmp_path / "history.db"
    store = Store(database)
    store.rename("https://docs.test", "Python docs")
    store.rename("https://packages.test", "Python packages")
    config = tmp_path / "jusi.toml"
    config.write_text(f'[web]\ndatabase = "{database}"\nendpoint = "http://127.0.0.1:{server.server_port}/agent"\napi_key = "test-only"\n')
    home = tmp_path / "home"
    home.mkdir()
    environment = {**os.environ, "JUSI_SOURCE_ROOT": str(source), "JUSI_WEB_TEST_PYTHON": sys.executable,
                   "JUSI_WEB_TEST_CONFIG": str(config), "HOME": str(home), "VD_DIR": str(home / "vd"),
                   "XDG_CONFIG_HOME": str(home), "XDG_DATA_HOME": str(home), "XDG_CACHE_HOME": str(home)}
    try:
        result = subprocess.run(["nvim", "--headless", "-u", "NONE", "-l", str(Path(__file__).with_name("web_e2e.lua"))],
                                env=environment, capture_output=True, text=True, timeout=100)
        assert result.returncode == 0, result.stdout + result.stderr + "\nrequests=" + repr(requests)
        assert [r["input"] for r in requests] == ["find cheese websites", "break search"]
        assert store.rows()[0]["url"] == "https://recovered.test"
        assert store.name("https://keep.test") == "Kept page"
        assert store.name("https://recovered.test") == "Recovered page"
        assert store.rows()[0]["open_count"] == 5
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
