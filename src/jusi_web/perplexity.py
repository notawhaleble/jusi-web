from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .routing import is_url


class SearchError(RuntimeError):
    pass


def citation_rows(response):
    """Read all structured search batches and citation annotations, never prose."""
    rows = {}

    def add(source):
        if not isinstance(source, dict):
            return
        url = source.get("url", "")
        if not isinstance(url, str) or not is_url(url):
            return
        row = rows.setdefault(url, {"url": url, "name": "", "title": "", "snippet": ""})
        for key in ("title", "snippet"):
            value = source.get(key)
            if isinstance(value, str) and value and not row[key]:
                row[key] = value

    output = response.get("output", [])
    if not isinstance(output, list):
        raise SearchError("Perplexity returned invalid source metadata")
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "search_results":
            results = item.get("results", [])
            if not isinstance(results, list):
                raise SearchError("Perplexity returned invalid search results")
            for source in results:
                add(source)
        contents = item.get("content", [])
        if not isinstance(contents, list):
            continue
        for content in contents:
            if isinstance(content, dict):
                annotations = content.get("annotations", [])
                if not isinstance(annotations, list):
                    continue
                for annotation in annotations:
                    if isinstance(annotation, dict) and annotation.get("type") == "url_citation":
                        add(annotation.get("url_citation", annotation))
    return list(rows.values())


def search(query, settings):
    key = settings.api_key or os.environ.get(settings.api_key_env, "")
    if not key:
        raise SearchError(f"Set {settings.api_key_env} to search with Perplexity; bookmarks and URLs work without it")
    request = urllib.request.Request(
        settings.endpoint,
        data=json.dumps({"effort": settings.effort, "input": query,
                         "instructions": settings.instructions}).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.timeout) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        # Avoid echoing API response bodies, which can contain request credentials.
        raise SearchError(f"Perplexity returned HTTP {exc.code}") from exc
    except (OSError, ValueError) as exc:
        raise SearchError(f"Perplexity request failed ({type(exc).__name__})") from exc
    if not isinstance(data, dict) or data.get("error") or data.get("status") not in {None, "completed"}:
        raise SearchError("Perplexity did not complete the search")
    return citation_rows(data)
