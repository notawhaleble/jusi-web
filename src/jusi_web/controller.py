from __future__ import annotations

import sqlite3
from jusi.editor_client import EditorDeliveryError

from .perplexity import SearchError, search
from .routing import is_url, resolve


class WebError(RuntimeError):
    pass


class Editor:
    """Keep the frontend identity private to Jusi; a slot is local to this client."""

    def __init__(self):
        from jusi import editor_client

        self.api = editor_client
        if not hasattr(editor_client, "close_url"):
            raise WebError("This Jusi installation lacks managed URL actions; install Jusi with open_url(slot=...) and close_url support")

    def close(self):
        self.api.close_url(slot="web")

    def open(self, url):
        self.api.open_url(url, slot="web")


class Controller:
    def __init__(self, store, settings, editor, present, searcher=search):
        self.store = store
        self.settings = settings
        self.editor = editor
        self.present = present
        self.searcher = searcher

    def submit(self, body, *, followup=False):
        try:
            if followup:
                # Retire the old page even when the new request displays a list
                # or the search fails. Closing is idempotent after manual close.
                self.editor.close()
            route = resolve(body, self.store.rows(bookmarks=True))
            if route.kind == "open":
                self.open_row(route.rows[0])
                # Include a newly visited, unnamed URL in the underlying sheet
                # so it can be named as soon as the user returns from the page.
                # Read after the acknowledged open has committed its visit.
                self.show("history" if is_url(body.strip()) else "bookmarks")
            elif route.kind == "bookmarks":
                self.present("bookmarks", route.rows, route.query)
            else:
                self.present("searching", [], route.query)
                route.rows = self.searcher(route.query, self.settings)
                for row in route.rows:
                    row["name"] = self.store.name(row["url"])
                self.present("citations", route.rows, route.query)
            return {"kind": route.kind, "count": len(route.rows)}
        except (SearchError, EditorDeliveryError, OSError, sqlite3.Error) as exc:
            raise WebError(str(exc)) from exc

    def open_row(self, row):
        url = row.get("url", "")
        if not is_url(url):
            raise WebError("Select a row with an absolute HTTP(S) URL")
        try:
            # Opening in the same slot replaces the previous projection, also
            # when drilling through citations rather than submitting a cell.
            self.editor.open(url)
            self.store.opened(url, row.get("title", ""))
        except (EditorDeliveryError, OSError, sqlite3.Error) as exc:
            raise WebError(str(exc)) from exc

    def show(self, kind):
        self.present(kind, self.store.rows(bookmarks=kind == "bookmarks"), "")
