import pytest
from jusi.editor_client import EditorDeliveryError

from jusi_web.config import Settings
from jusi_web.controller import Controller, WebError
from jusi_web.perplexity import SearchError
from jusi_web.store import Store


class Editor:
    def __init__(self):
        self.events = []
        self.current = None

    def close(self):
        self.events.append("close")
        self.current = None

    def open(self, url):
        self.events.append(("open", url))
        self.current = url


def test_followups_from_full_subset_and_citation_sheets(tmp_path):
    store = Store(tmp_path / "db")
    store.rename("https://docs.test", "Python docs")
    store.rename("https://packages.test", "Python packages")
    editor, sheets, searches = Editor(), [], []

    def search(query, settings):
        searches.append(query)
        if query == "broken search":
            raise SearchError("API unavailable")
        return [{"url": "https://result.test", "title": "Result"}]

    client = Controller(store, Settings(store.path), editor, lambda *args: sheets.append(args), search)
    client.submit("")
    assert len(sheets[-1][1]) == 2
    client.submit("py", followup=True)
    assert sheets[-1][0] == "bookmarks" and len(sheets[-1][1]) == 2
    client.submit("pydoc", followup=True)
    assert editor.current == "https://docs.test"
    # A new list request must also retire the old page.
    client.submit("py", followup=True)
    assert editor.current is None
    client.submit("a cheese shop", followup=True)
    assert sheets[-1][0] == "citations"
    client.open_row(sheets[-1][1][0])
    assert editor.current == "https://result.test"
    # Closing the browser cannot change Controller/client identity or sheet.
    editor.close()
    client.open_row(sheets[-1][1][0])
    assert store.rows()[0]["open_count"] == 2
    with pytest.raises(WebError, match="API unavailable"):
        client.submit("broken search", followup=True)
    assert editor.current is None
    client.submit("https://next.test", followup=True)
    assert editor.events[-2:] == ["close", ("open", "https://next.test")]
    assert searches == ["a cheese shop", "broken search"]


def test_search_titles_do_not_create_bookmarks(tmp_path):
    store = Store(tmp_path / "db")
    client = Controller(store, Settings(store.path), Editor(), lambda *args: None)
    client.open_row({"url": "https://title.test", "title": "Automatic title"})
    assert store.rows(bookmarks=True) == []


def test_direct_url_prompts_show_current_history(tmp_path):
    store = Store(tmp_path / "db")
    editor, sheets = Editor(), []
    client = Controller(store, Settings(store.path), editor, lambda *args: sheets.append(args))
    url = "https://direct.test/?q=1#section"

    for visits in (1, 2):
        client.submit(f"  {url}\n", followup=visits > 1)
        kind, rows, query = sheets[-1]
        assert kind == "history" and query == ""
        assert len(rows) == 1
        assert rows[0]["url"] == url and rows[0]["open_count"] == visits
        assert rows[0]["last_opened"]
        assert rows[0]["name"] == ("" if visits == 1 else "Direct page")
        # The history row provides the URL used by the sheet's name setter.
        store.rename(rows[0]["url"], "Direct page")

    client.submit("Direct page", followup=True)
    assert editor.current == url
    assert sheets[-1][0] == "bookmarks"
    assert store.rows()[0]["open_count"] == 3


def test_unacknowledged_direct_url_does_not_enter_history(tmp_path):
    class FailedEditor(Editor):
        def open(self, url):
            raise EditorDeliveryError("Open failed")

    store = Store(tmp_path / "db")
    sheets = []
    client = Controller(store, Settings(store.path), FailedEditor(), lambda *args: sheets.append(args))
    with pytest.raises(WebError, match="Open failed"):
        client.submit("https://failed.test")
    assert store.rows() == []
    assert sheets == []
