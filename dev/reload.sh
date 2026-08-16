#!/usr/bin/env bash
# Fully reload the plugin inside the running Sublime Text.
#
# Sublime re-imports a package's top-level plugin files when they change, but
# leaves already-imported subpackages in sys.modules, so edits under markdownx/
# appear in inspect.getsource() while the stale module keeps executing.
#
# Order matters here. unload_plugin has to run while the entry point is still in
# sys.modules -- it is what unregisters the old command classes, and skipping it
# leaves another duplicate set behind on every single reload. Only then are the
# subpackage modules purged, so the fresh import picks up every edit.
#
# Expect commands to end up registered twice after the first reload of a
# session: Sublime's own file watcher reloads the package as well, and the two
# paths race. It settles at two rather than growing, and is harmless --
# run_command dispatches to the first match and the duplicate listener's extra
# render is dropped by the debounce generation check. A fresh Sublime start
# registers once. This only affects development, never an installed copy.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTRY="MarkdownX.markdownx_plugin"

find "$DIR/.." -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

PROBE_TIMEOUT=30 "$DIR/probe.sh" "
import sys, sublime_plugin, traceback

# Close previews and stop the HTTP server first. Purging sys.modules skips
# plugin_unloaded, and the server thread would otherwise keep its port with
# nothing left referencing it -- one orphan listener per reload.
try:
    from MarkdownX.markdownx import browser, surface
    for _p in surface.all_previews():
        _p.close()
    browser.close_all()
except Exception:
    pass

# Unregisters the old commands and event listeners.
sublime_plugin.unload_plugin('${ENTRY}')

stale = sorted(m for m in sys.modules if m == 'MarkdownX' or m.startswith('MarkdownX.'))
for name in stale:
    del sys.modules[name]

try:
    # The probe is deliberately not reloaded here. Reloading it mid-request
    # resets its seen-request id, so it re-runs the very request doing the
    # reloading. Edit the probe and let Sublime pick it up on its own.
    sublime_plugin.reload_plugin('${ENTRY}')
    report(purged=len(stale), reloaded=True)
except Exception:
    report(purged=len(stale), error=traceback.format_exc())
"
