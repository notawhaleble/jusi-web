from concurrent.futures import ThreadPoolExecutor

from jusi_web.routing import resolve, is_url, followup_body
from jusi_web.store import Store


def test_routing(tmp_path):
    store = Store(tmp_path / "web.db")
    for name, url in [("Python docs", "https://python.org/docs"), ("Python packages", "https://pypi.org"),
                      ("Other", "https://other.test")]:
        store.rename(url, name)
    rows = store.rows(bookmarks=True)
    assert resolve("", rows).kind == "bookmarks"
    assert resolve("https://python.org/?q=a#b", rows).rows == [{"url": "https://python.org/?q=a#b"}]
    assert resolve("PYTHON DOCS", rows).rows[0]["name"] == "Python docs"
    assert resolve("pydoc", rows).kind == "open"
    assert len(resolve("py", rows).rows) == 2
    assert resolve("py", rows).kind == "bookmarks"
    assert resolve("find a cheese shop", rows).kind == "search"
    store.rename("https://duplicate.test", "Python docs")
    assert resolve("Python docs", store.rows(bookmarks=True)).kind == "bookmarks"


def test_urls_and_literal_body():
    for url in ["https://example.com/?x=1&y=2#foo", "http://localhost:8000", "https://пример.рф"]:
        assert is_url(url)
    for value in ["example.com", "file:///tmp/file", "https://", "https://a b", "https://a\n", "https://[bad"]:
        assert not is_url(value)
    assert followup_body("%%web\nquery") == "query"
    assert followup_body("%%website\nquery") == "%%website\nquery"
    assert followup_body("some\nmultiline query") == "some\nmultiline query"


def test_persistent_edits_and_concurrent_visits(tmp_path):
    path = tmp_path / "web.db"
    store = Store(path)
    url = "https://example.com/?q=1#part"
    store.rename(url, "Example")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: Store(path).opened(url, "Title"), range(20)))
    assert Store(path).rows()[0]["open_count"] == 20
    assert store.rows()[0]["name"] == "Example"
    store.rename(url, "")
    assert store.rows(bookmarks=True) == []
    assert store.rows()[0]["title"] == "Title"
    store.opened(url)
    assert store.rows()[0]["title"] == "Title"
    store.opened("https://example.com/?q=2#part")
    assert len(store.rows()) == 2
