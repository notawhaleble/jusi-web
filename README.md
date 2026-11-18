# jusi-web

Jusi 1.0 plugin for opening URLs, named bookmarks, and Perplexity search results
in WebBuffers. Its VisiData application stays alive when a page closes.

## Install

Install in the Jusi target's Python environment:

```sh
python -m pip install -e /path/to/jusi-web
```

Requires VisiData 3 and Jusi with the generic managed-URL editor actions
`open_url(url, slot=...)` and `close_url(slot=...)`, plus `JusiWebBuffer` in the
editor host (provided by jusi-neovim). Older Jusi builds fail with an explicit
message rather than silently accumulating pages.

The required generic core extension is included in
[integration/jusi-managed-urls.patch](integration/jusi-managed-urls.patch), with
[installation notes](integration/README.md). It has been applied to the sibling
Jusi checkout; use that checkout for both the service and Lua frontend until a
release includes these APIs.

## Use

```python
%%web
https://docs.python.org/3/
```

The initial body and every followup use the same routing, regardless of which
sheet is currently displayed:

1. Empty body or cell bootstrap: show all named bookmarks.
2. Absolute HTTP(S) URL occupying the whole body: open it directly, with refreshed
   history underneath so the URL can be named as a bookmark on returning to VisiData.
3. Exact bookmark name, ignoring case: open it if unique.
4. Otherwise, fuzzy-match bookmark names. One match opens; multiple matches
   display a bookmarks subset. Matching is case-insensitive subsequence matching
   with whitespace ignored (`pydoc` matches `Python docs`).
5. No bookmark match: search Perplexity and show structured source links as rows.

Enter/drilldown opens the selected row. `gB` shows all bookmarks; `gH` shows
history. Normal VisiData navigation, filtering, editing and copy/open work.
Each Perplexity query is independent; earlier searches are not sent as chat
history. Result sheets remain available in the normal VisiData sheet stack.
Search failures are recoverable: the same client accepts the next followup.
Searches run outside the VisiData UI thread. Citations appear automatically
when the search finishes, including after the UI has been idle. This version does not advertise
JusiInterrupt for application work.

Each client has one managed page, shown in the same window as its VisiData
application. Opening another row replaces that page without creating a split.
Replacement deletes the old buffer across all tabs, including when it is hidden.
If neither the page nor VisiData is visible, a new window reveals the same client
and shows the replacement there; windows displaying unrelated content are preserved.
Every followup first closes its previous page, including followups that display
bookmarks, ambiguous matches, or an error. The next opened page uses a new web
buffer. Followups restore VisiData in that window before showing the next view.
Closing the page manually leaves the sheet and client running; use
`JusiToggleFocus` from the cell to reveal the sheet again. Use a
separate `%%web` cell to retain another page. Pages in other clients are never
replaced. Closing the source client leaves its last delivered page available,
following Jusi's URL export lifetime.

## Bookmarks and history

Edit a row's `name` using normal VisiData editing to bookmark its URL. Changes
are persisted immediately, including undo. A nonempty name makes the URL
searchable; clearing the name removes bookmark status and retains visit history.
Names can also be edited directly in search results, before opening a page.
Automatically supplied titles never become bookmark names.

History has one row per exact URL; opening a page updates its time and visit
count without replacing its name. Query strings and fragments are preserved.
Only acknowledged opens count as visits. Following links or redirects inside
the browser does not feed navigation history back into this plugin.

The SQLite database is shared across notebooks using the same target-side state
directory. Separate target machines have separate stores. Multiple cells can
edit the same database safely. Views can be refreshed with `gB` or `gH`.

## Configuration

Optional target configuration:

```toml
[web]
# Defaults to $JUSI_STATE_HOME/plugins/web/history.sqlite3, or
# ${XDG_STATE_HOME:-~/.local/state}/jusi/plugins/web/history.sqlite3.
database = "~/.local/state/jusi/plugins/web/history.sqlite3"
api_key_env = "PERPLEXITY_API_KEY"
effort = "low" # fast, low, medium
timeout = 120
# system_prompt = "Find relevant pages and cite direct authoritative sources."
# system_prompt_file = "/absolute/path/to/web-prompt.txt"
```

API keys are read from the target environment when searching; bookmarks and
explicit URLs need no key. An explicit `api_key` is also supported. Prompt files
are read on the target; relative paths resolve from the target working directory.
`system_prompt_file` takes precedence over `system_prompt`.

Uses Perplexity's Agent API, `POST https://api.perplexity.ai/v1/agent`, with a
default link-finding system instruction and configurable effort. URLs are taken
from every structured `search_results` output and URL citation annotation,
deduplicated in returned order; generated prose is never parsed for links.
The default instruction asks Perplexity to find and cite the official destination
when a request clearly references a site (for example, Google should include
`https://www.google.com`), and to keep its answer to short labels with useful
citations. This is best-effort guidance; custom prompts replace it.
See the [Agent API guide](https://docs.perplexity.ai/docs/agent-api/quickstart)
and [source extraction contract](https://docs.perplexity.ai/docs/agent-api/prompt-guide).
`endpoint` can override the endpoint for a compatible local service or testing.

## Development

```sh
python -m pip install -e '.[test]'
python -m pytest
```

The integration tests use real subprocesses, a PTY-hosted VisiData application,
and headless Neovim with a substitute WebBuffer command. They do not exercise
Electron rendering or make paid Perplexity requests.
