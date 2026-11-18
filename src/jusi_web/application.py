from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import traceback

from jusi.visidata_support import initialize_visidata

from .config import Settings
from .control import ControlServer
from .controller import Controller, Editor, WebError
from .store import Store


def run_application(path, socket_path):
    launch = json.loads(path.read_text(encoding="utf-8"))
    path.unlink()
    settings = Settings.from_dict(launch["config"])
    store = Store(settings.database)
    vd = initialize_visidata(open_name="web-selection.txt")
    # Executor/control threads can publish after VisiData becomes idle. Keep
    # its UI polling the command queue: curses.ungetch from another thread does
    # not reliably interrupt a getch already blocked on terminal input.
    vd.timeouts_before_idle = -1
    from visidata import BaseSheet, Column, ColumnItem, CommandLogRow, Sheet

    pending = deque()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jusi-web")

    def background(function, *args):
        future = executor.submit(function, *args)

        def finished(result):
            if not result.cancelled() and result.exception() is not None:
                # Unexpected application failures must reach core as process
                # loss, rather than leaving a healthy-looking dead UI.
                traceback.print_exception(result.exception(), file=sys.stderr)
                sys.stderr.flush()
                os._exit(1)

        future.add_done_callback(finished)
        return future

    def present(kind, rows, query):
        pending.append((kind, rows, query))
        vd.queueCommand("jusi-web-present")

    controller = Controller(store, settings, Editor(), present)

    class WebSheet(Sheet):
        def setModified(self):
            # Name setters commit immediately. There are no pending sheet
            # writes to save when leaving a view; normal edit undo still works.
            pass

        def openRow(self, row, rowidx=None):
            if row is not None:
                selected = dict(row)
                background(open_selected, selected)
            return None

    def set_name(col, row, value):
        # Column's normal edit/undo machinery calls this setter, so both edits
        # and undo persist. No deferred-write or explicit save step is needed.
        store.rename(row["url"], value)
        row["name"] = str(value).strip()

    def sheet(kind, rows, query=""):
        columns = [
            Column("name", width=24, getter=lambda c, r: r.get("name", ""), setter=set_name),
            Column("url", width=64, getter=lambda c, r: r["url"]),
            Column("title", width=40, getter=lambda c, r: r.get("title", "")),
        ]
        if kind == "history":
            columns.extend([Column("last_opened", width=27, getter=lambda c, r: r.get("last_opened", "")),
                            Column("open_count", type=int, getter=lambda c, r: r.get("open_count", 0))])
        if kind == "citations":
            columns.append(Column("snippet", width=70, getter=lambda c, r: r.get("snippet", "")))
        if kind == "error":
            columns = [ColumnItem("error", width=100)]
        view = WebSheet(f"web:{kind}" + (f":{query}" if query else ""), rows=rows, columns=columns)
        # Undo reserves the first command-log row for sheet creation. Embedded
        # sheets have no CLI open command, so supply that no-op row explicitly.
        view.cmdlog_sheet.rows.append(CommandLogRow(longname="jusi-web-view", sheet=view.name))
        return view

    @BaseSheet.command("", "jusi-web-view", "web view creation marker", replay=False)
    def view_marker(current):
        pass

    @BaseSheet.command("", "jusi-web-present", "show web request result", replay=False)
    def drain(current):
        while pending:
            kind, rows, query = pending.popleft()
            vd.push(sheet(kind, rows, query))
            if kind == "citations" and not rows:
                vd.warning("Perplexity returned no usable links")

    @BaseSheet.command("gB", "jusi-web-bookmarks", "show all named bookmarks", replay=False)
    def bookmarks(current):
        controller.show("bookmarks")

    @BaseSheet.command("gH", "jusi-web-history", "show history", replay=False)
    def history(current):
        controller.show("history")

    def report(error):
        present("error", [{"error": str(error)}], "")

    def open_selected(row):
        try:
            controller.open_row(row)
        except WebError as exc:
            report(exc)

    def submit(body, followup):
        try:
            return {"ok": True, **controller.submit(body, followup=followup)}
        except WebError as exc:
            report(exc)
            return {"ok": False, "error": str(exc)}

    def dispatch(request):
        if request.get("type") != "followup":
            return {"ok": False, "error": "Unknown web control request"}
        return executor.submit(submit, str(request.get("body", "")), True).result()

    server = ControlServer(socket_path, dispatch)
    server.start()
    initial = sheet("bookmarks", store.rows(bookmarks=True))

    @BaseSheet.command("", "jusi-web-start", "process initial web request", replay=False)
    def start(current):
        if str(launch.get("body", "")).strip():
            background(submit, str(launch["body"]), False)

    if str(launch.get("body", "")).strip():
        vd.queueCommand("jusi-web-start")
    try:
        vd.run(initial)
    finally:
        server.close()
        executor.shutdown(wait=False, cancel_futures=True)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("jusi-web application requires launch and control paths")
    raise SystemExit(run_application(Path(sys.argv[1]), sys.argv[2]))
