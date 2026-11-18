from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit
import unicodedata


def is_url(text):
    if not text or len(text) > 8192 or any(char.isspace() or unicodedata.category(char).startswith("C") for char in text):
        return False
    try:
        parts = urlsplit(text)
        return parts.scheme in {"http", "https"} and bool(parts.hostname)
    except ValueError:
        return False


def followup_body(body):
    # Jusi delivers literal bodies; tolerate a full cell from an editor caller.
    first, sep, rest = body.partition("\n")
    if first.strip() == "%%web":
        return rest if sep else ""
    return body


def fuzzy_match(query, name):
    """Casefolded subsequence matching, with all whitespace ignored."""
    query = "".join(query.casefold().split())
    name = iter("".join(name.casefold().split()))
    return bool(query) and all(any(char == candidate for candidate in name) for char in query)


@dataclass
class Route:
    kind: str
    rows: list
    query: str = ""


def resolve(body, bookmarks):
    query = body.strip()
    if not query:
        return Route("bookmarks", bookmarks)
    if is_url(query):
        return Route("open", [{"url": query}])
    exact = [row for row in bookmarks if row["name"].casefold() == query.casefold()]
    matches = exact or [row for row in bookmarks if fuzzy_match(query, row["name"])]
    if matches:
        return Route("open" if len(matches) == 1 else "bookmarks", matches, query)
    return Route("search", [], query)
