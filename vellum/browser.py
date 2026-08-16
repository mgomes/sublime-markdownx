"""Browser previews: one session per document, backed by the local server."""

import os
import traceback
import webbrowser

import sublime

from . import export, server

#: Matches the pane's debounce so both targets update at the same pace.
DEBOUNCE_MS = 120

_sessions = {}


class BrowserPreview:
    """Keeps one browser session fed with rendered HTML."""

    def __init__(self, source, settings):
        self.source = source
        self.settings = settings
        self.key = "b%d" % source.buffer_id()
        self.generation = 0
        self.last_source_line = -1
        self.suppress_echo_until = 0

        name = source.file_name()
        self.session = server.open_session(
            self.key,
            os.path.basename(name) if name else (source.name() or "Untitled"),
            os.path.dirname(name) if name else None,
        )
        self.session.on_scroll = self._on_browser_scroll

    # -- rendering -------------------------------------------------------

    def render(self):
        if not self.alive():
            return

        text = self.source.substr(sublime.Region(0, self.source.size()))
        try:
            result = export.render_body(
                text,
                base_url=server.base_url_for(self.key),
                asset_query=server.asset_query(self.key),
                settings=self.settings,
            )
            html = result["html"]
        except Exception:
            print("[vellum] browser render failed:\n" + traceback.format_exc())
            html = '<div class="error">%s</div>' % traceback.format_exc()

        self.session.update(html)

    def schedule(self):
        self.generation += 1
        generation = self.generation

        def fire():
            if self.alive() and generation == self.generation:
                self.render()

        sublime.set_timeout_async(fire, DEBOUNCE_MS)

    # -- scroll sync -----------------------------------------------------

    def sync_scroll(self):
        """Push the editor's first visible line out to the browser."""
        if not (self.alive() and self.settings.get("scroll_sync", True)):
            return
        if self.session.client_count() == 0:
            return

        line, _ = self.source.rowcol(self.source.visible_region().begin())
        if line == self.last_source_line:
            return

        # A scroll the browser itself asked for must not bounce straight back.
        if _now_ms() < self.suppress_echo_until:
            self.last_source_line = line
            return

        self.last_source_line = line
        self.session.scroll_to(line)

    def _on_browser_scroll(self, line):
        """Scroll the editor to `line`. Called from a server thread."""
        if not self.settings.get("scroll_sync", True):
            return

        def apply():
            if not self.alive():
                return
            self.suppress_echo_until = _now_ms() + 400
            self.last_source_line = line
            point = self.source.text_point(max(0, line), 0)
            target = self.source.text_to_layout(point)
            position = self.source.viewport_position()
            self.source.set_viewport_position((position[0], target[1]), animate=False)

        sublime.set_timeout(apply, 0)

    # -- lifecycle -------------------------------------------------------

    def alive(self):
        return self.source.is_valid()

    def open_in_browser(self):
        url = server.url_for(self.key)
        if url:
            webbrowser.open(url)

    def close(self):
        self.session.on_scroll = None
        server.close_session(self.key)


def _now_ms():
    import time

    return int(time.monotonic() * 1000)


# -- module level --------------------------------------------------------


def get(source):
    preview = _sessions.get(source.buffer_id())
    if preview and not preview.alive():
        forget(source.buffer_id())
        return None
    return preview


def forget(buffer_id):
    preview = _sessions.pop(buffer_id, None)
    if preview:
        preview.close()


def all_previews():
    return list(_sessions.values())


def open_for(source, settings):
    """Open (or focus) a browser preview for `source`."""
    existing = get(source)
    if existing:
        existing.settings = settings
        existing.open_in_browser()
        return existing

    preview = BrowserPreview(source, settings)
    _sessions[source.buffer_id()] = preview
    preview.render()
    preview.open_in_browser()
    return preview


def close_all():
    for buffer_id in list(_sessions):
        forget(buffer_id)
