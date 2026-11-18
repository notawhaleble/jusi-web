import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

import pytest

from jusi_web.config import Settings
from jusi_web.perplexity import SearchError, citation_rows, search


def test_sources_from_all_batches_and_annotations():
    result = citation_rows({"output": [
        {"type": "search_results", "results": [{"url": "https://a.test", "title": "A"}]},
        {"type": "search_results", "results": [{"url": "https://b.test"}, {"url": "https://a.test", "snippet": "Details"}]},
        {"type": "message", "content": [{"type": "output_text", "text": "https://invented.test",
            "annotations": [{"type": "url_citation", "url": "https://c.test", "title": "C"},
                            {"type": "url_citation", "url": "file:///bad"}]}]},
    ]})
    assert [row["url"] for row in result] == ["https://a.test", "https://b.test", "https://c.test"]
    assert result[0]["snippet"] == "Details"
    assert result[0]["name"] == ""


def test_malformed_sources_are_recoverable():
    for response in [{"output": None}, {"output": [{"type": "search_results", "results": None}]}]:
        with pytest.raises(SearchError):
            citation_rows(response)


def test_http_request_and_recovery(tmp_path, monkeypatch):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(429 if len(requests) == 1 else 200)
            self.end_headers()
            self.wfile.write(json.dumps({"status": "completed", "output": [
                {"type": "search_results", "results": [{"url": "https://answer.test"}]}]}).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        monkeypatch.setenv("TEST_PPLX_KEY", "test-key")
        settings = Settings(tmp_path / "db", api_key_env="TEST_PPLX_KEY",
                            endpoint=f"http://127.0.0.1:{server.server_port}/agent")
        with pytest.raises(SearchError, match="429"):
            search("first", settings)
        assert search("second", settings)[0]["url"] == "https://answer.test"
        assert requests[1]["input"] == "second"
        assert "messages" not in requests[1]
        assert requests[1]["instructions"] == settings.instructions
        assert requests[1]["effort"] == "low"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
