#!/usr/bin/env bash
# Fully reload the plugin inside the running Sublime Text.
#
# Sublime re-imports a package's top-level plugin files when they change, but
# leaves already-imported subpackages in sys.modules, so edits under markdownx/
# appear in inspect.getsource() while the stale module keeps executing. Purging
# the subpackage first and then reloading the entry point picks up every change.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

find "$DIR/.." -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

PROBE_TIMEOUT=30 "$DIR/probe.sh" '
import sys, sublime_plugin, traceback

# Shut the HTTP server down before dropping the modules. Purging sys.modules
# skips plugin_unloaded, and the server thread would then keep its port with
# nothing left referencing it -- one orphan listener per reload.
try:
    from MarkdownX.markdownx import browser, surface
    for _p in surface.all_previews():
        _p.close()
    browser.close_all()
except Exception:
    pass

stale = sorted(m for m in sys.modules if m == "MarkdownX" or m.startswith("MarkdownX."))
for name in stale:
    del sys.modules[name]
try:
    # The probe is deliberately not reloaded here. Reloading it mid-request
    # resets its seen-request id, so it re-runs the very request doing the
    # reloading. Edit probe.py and let Sublime pick it up on its own.
    sublime_plugin.reload_plugin("MarkdownX.markdownx_plugin")
    report(purged=len(stale), reloaded=True)
except Exception:
    report(purged=len(stale), error=traceback.format_exc())
'
