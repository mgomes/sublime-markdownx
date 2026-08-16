#!/usr/bin/env bash
# Send a Python snippet to the running Sublime Text and print what it reports.
#
# The snippet runs inside Sublime's plugin host with `sublime` in scope and a
# `report(**kwargs)` hook for returning values. Snippets that wait on Sublime to
# lay out a view call `defer()` up front and `done()` when finished. Usage:
#
#   dev/probe.sh 'report(build=sublime.version())'
#   dev/probe.sh < some_snippet.py
set -euo pipefail

PROBE_DIR="${HOME}/.markdownx-probe"
mkdir -p "$PROBE_DIR"

source_text="${1:-$(cat)}"
timeout="${PROBE_TIMEOUT:-15}"
request_id="$$-${RANDOM}-$(date +%s)"

rm -f "$PROBE_DIR/response.json"
python3 -c '
import json, sys
json.dump({"source": sys.argv[1], "id": sys.argv[3]}, open(sys.argv[2], "w"))
' "$source_text" "$PROBE_DIR/request.json" "$request_id"

# The response is only ours once its echoed id matches; a reloaded plugin can
# briefly leave an older response on disk.
for _ in $(seq 1 $((timeout * 4))); do
    if [ -f "$PROBE_DIR/response.json" ]; then
        if python3 -c '
import json, sys
try:
    sys.exit(0 if json.load(open(sys.argv[1]))["id"] == sys.argv[2] else 1)
except Exception:
    sys.exit(1)
' "$PROBE_DIR/response.json" "$request_id"; then
            cat "$PROBE_DIR/response.json"
            echo
            exit 0
        fi
    fi
    sleep 0.25
done

echo "probe: no response after ${timeout}s (is Sublime running with markdownx_dev_probe.py installed?)" >&2
exit 1
