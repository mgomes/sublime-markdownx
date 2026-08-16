"""Development-only bridge that lets an external process drive Sublime Text.

Sublime exposes no CLI for running commands, which makes a plugin hard to test
without a human clicking through the UI. This module polls a request file for a
JSON payload, evaluates it on the main thread, and writes the result back to a
response file, so the whole plugin can be exercised from a shell script.

It is not loaded in normal use: ``vellum.py`` never imports it, and it does
nothing unless ``VELLUM_PROBE_DIR`` exists on disk.
"""

import json
import os
import traceback

import sublime
import sublime_plugin

PROBE_DIR = os.path.expanduser("~/.vellum-probe")
REQUEST = os.path.join(PROBE_DIR, "request.json")
RESPONSE = os.path.join(PROBE_DIR, "response.json")
POLL_MS = 250

_last_seen = None


def _respond(payload):
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
    global _last_seen

    if os.path.isdir(PROBE_DIR) and os.path.exists(REQUEST):
        try:
            stamp = os.path.getmtime(REQUEST)
        except OSError:
            stamp = None

        if stamp is not None and stamp != _last_seen:
            _last_seen = stamp
            try:
                with open(REQUEST, encoding="utf-8") as handle:
                    request = json.load(handle)
                _run(request["source"], _respond)
            except Exception:
                _respond({"ok": False, "error": traceback.format_exc()})

    sublime.set_timeout(_poll, POLL_MS)


def plugin_loaded():
    print("[vellum-probe] watching", REQUEST)
    sublime.set_timeout(_poll, POLL_MS)
