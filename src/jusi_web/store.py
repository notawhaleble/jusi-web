from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


class Store:
    """One URL per row; independent connections let cells safely share a database."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS pages (
                url TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '', last_opened TEXT,
                open_count INTEGER NOT NULL DEFAULT 0)""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def rows(self, *, bookmarks=False):
        where = "WHERE name != ''" if bookmarks else "WHERE open_count > 0 OR name != ''"
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                f"SELECT * FROM pages {where} ORDER BY last_opened DESC, name COLLATE NOCASE, url")]

    def name(self, url):
        with self.connect() as db:
            row = db.execute("SELECT name FROM pages WHERE url=?", (url,)).fetchone()
            return row[0] if row else ""

    def rename(self, url, name):
        with self.connect() as db:
            db.execute("""INSERT INTO pages(url,name) VALUES (?,?)
                ON CONFLICT(url) DO UPDATE SET name=excluded.name""", (url, str(name).strip()))

    def opened(self, url, title=""):
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute("""INSERT INTO pages(url,title,last_opened,open_count) VALUES (?,?,?,1)
                ON CONFLICT(url) DO UPDATE SET last_opened=excluded.last_opened,
                open_count=pages.open_count+1,
                title=CASE WHEN excluded.title != '' THEN excluded.title ELSE pages.title END""",
                       (url, title, now))
