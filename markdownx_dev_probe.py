"""Development-only bridge that lets an external process drive Sublime Text.

Sublime exposes no CLI for running commands, which makes a plugin hard to test
without a human clicking through the UI. This module polls a request file for a
JSON payload, evaluates it on the main thread, and writes the result back to a
response file, so the whole plugin can be exercised from a shell script.

It is not loaded in normal use: ``markdownx.py`` never imports it, and it does
nothing unless ``VELLUM_PROBE_DIR`` exists on disk.
"""

import json
import os
import traceback

import sublime
import sublime_plugin

PROBE_DIR = os.path.expanduser("~/.markdownx-probe")
REQUEST = os.path.join(PROBE_DIR, "request.json")
RESPONSE = os.path.join(PROBE_DIR, "response.json")
POLL_MS = 250

#: Nonce of the last request executed. Requests carry an id rather than being
#: identified by mtime, because reloading the plugin resets this module's state
#: and an mtime-based check would then re-run the request that triggered it.
_last_id = None


def _respond(payload, request_id=None):
    payload = dict(payload, id=request_id)
    tmp = RESPONSE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, default=repr)
    os.replace(tmp, RESPONSE)


def _run(source, finish):
    """Exec `source`, collecting values it passes to ``report``.

    Snippets that only touch synchronous API report and return immediately.
    Anything that has to wait for Sublime to lay out a view calls ``defer()``
    first and ``done()`` when its callbacks have run, since layout figures are
    not settled until after the current tick.
    """
    captured = {}
    state = {"deferred": False}

    def report(**kwargs):
        captured.update(kwargs)

    def defer():
        state["deferred"] = True

    def done():
        finish({"ok": True, "result": captured})

    scope = {
        "sublime": sublime,
        "sublime_plugin": sublime_plugin,
        "report": report,
        "defer": defer,
        "done": done,
        "os": os,
        "json": json,
    }
    exec(compile(source, "<probe>", "exec"), scope)

    if not state["deferred"]:
        finish({"ok": True, "result": captured})


def _poll():
    global _last_id

    if os.path.isdir(PROBE_DIR) and os.path.exists(REQUEST):
        request = None
        try:
            with open(REQUEST, encoding="utf-8") as handle:
                request = json.load(handle)
        except (OSError, ValueError):
            pass  # Half-written request; it will be complete next tick.

        if request is not None and request.get("id") != _last_id:
            request_id = request.get("id")
            _last_id = request_id
            try:
                _run(request["source"], lambda p: _respond(p, request_id))
            except Exception:
                _respond({"ok": False, "error": traceback.format_exc()}, request_id)

    sublime.set_timeout(_poll, POLL_MS)


def plugin_loaded():
    print("[markdownx-probe] watching", REQUEST)
    sublime.set_timeout(_poll, POLL_MS)
