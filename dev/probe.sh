#!/usr/bin/env bash
# Send a Python snippet to the running Sublime Text and print what it reports.
#
# The snippet runs inside Sublime's plugin host with `sublime` in scope and a
# `report(**kwargs)` hook for returning values. Usage:
#
#   dev/probe.sh 'report(build=int(sublime.version()))'
#   dev/probe.sh < some_snippet.py
set -euo pipefail

PROBE_DIR="${HOME}/.vellum-probe"
mkdir -p "$PROBE_DIR"

source_text="${1:-$(cat)}"
timeout="${PROBE_TIMEOUT:-15}"

rm -f "$PROBE_DIR/response.json"
python3 -c '
import json, sys
json.dump({"source": sys.argv[1]}, open(sys.argv[2], "w"))
' "$source_text" "$PROBE_DIR/request.json"

for _ in $(seq 1 $((timeout * 4))); do
    if [ -f "$PROBE_DIR/response.json" ]; then
        cat "$PROBE_DIR/response.json"
        echo
        exit 0
    fi
    sleep 0.25
done

echo "probe: no response after ${timeout}s (is Sublime running with dev/probe.py installed?)" >&2
exit 1
