"""The preview pane: its lifecycle, live updates, and scroll sync.

The pane is a scratch view holding a single block phantom rather than an
``HtmlSheet``. Both render minihtml, but ``HtmlSheet`` exposes no viewport at
all -- ``sheet.view()`` is None and it has no scroll methods -- so it can
neither be scrolled to follow the editor nor hold its position across an update.
A phantom in an ordinary view keeps ``set_viewport_position`` available, and
replacing the phantom leaves the scroll position untouched.
"""

import sublime

from . import document

#: Marker settings key identifying a preview view and the buffer it follows.
SOURCE_ID = "markdownx_source_id"
IS_PREVIEW = "markdownx_preview"

#: How long to wait after the last keystroke before re-rendering.
DEBOUNCE_MS = 120

#: How often to check whether the editor has been scrolled. Sublime has no
#: scroll event, so following the editor means sampling its viewport.
SYNC_POLL_MS = 100

PHANTOM_KEY = "markdownx"

#: Room left for the vertical scrollbar when sizing the page.
_SCROLLBAR_ALLOWANCE = 16

#: Horizontal padding and border the stylesheet applies inside table rows and
#: code blocks, which is not part of the character budget.
_ROW_PADDING_PX = 26

_previews = {}


class Preview:
    """One preview pane bound to one source view."""

    def __init__(self, source, view, settings):
        self.source = source
        self.view = view
        self.settings = settings
        self.anchors = []
        self.generation = 0
        self.last_source_line = -1
        self.last_width = 0

    # -- rendering -------------------------------------------------------

    def fit_settings(self):
        """Add width limits derived from the pane's current size.

        minihtml has no width property and no horizontal scrolling, so the
        widest element sets the width of the whole document -- one long code
        line or wide table stops every paragraph from wrapping at the pane edge.
        Both are therefore bounded to what the pane can actually show.

        The character width comes from ``em_width()`` on the source view, scaled
        by the ratio between the preview's code size and the editor's font size,
        since both render in the same monospace face.
        """
        settings = dict(self.settings)

        editor_size = self.source.settings().get("font_size") or 12
        em = self.source.em_width() or (editor_size * 0.6)
        code_size = max(9, int(settings.get("font_size") or (editor_size + 1)) * 0.92)
        char_px = em * (code_size / float(editor_size))

        width = self.view.viewport_extent()[0]
        if width > 0 and char_px > 0:
            padding = int(settings.get("font_size") or (editor_size + 1))
            page = int(width - (2 * padding) - _SCROLLBAR_ALLOWANCE)
            settings["page_width"] = max(200, page)

            # _ROW_PADDING_PX is the horizontal padding the stylesheet puts on
            # table rows and code blocks, which sits outside the character
            # budget and would otherwise push the last column into a wrap.
            usable = page - _ROW_PADDING_PX
            available = max(20, int(usable / char_px) - 1)
            settings["code_max_width"] = min(
                available, settings.get("code_max_width") or available
            )
            settings["table_max_width"] = min(
                available, settings.get("table_max_width") or available
            )

        return settings

    def render(self):
        """Re-render the source into the pane, preserving scroll position."""
        if not self.alive():
            return

        text = self.source.substr(sublime.Region(0, self.source.size()))
        try:
            html, anchors = document.render(self.source, text, self.fit_settings())
        except Exception as error:
            import traceback

            print("[markdownx] render failed:\n" + traceback.format_exc())
            html = document.render_error(self.source, str(error), traceback.format_exc()[-800:])
            anchors = []

        self.anchors = anchors
        self.last_width = self.view.viewport_extent()[0]
        position = self.view.viewport_position()

        self.view.erase_phantoms(PHANTOM_KEY)
        self.view.add_phantom(
            PHANTOM_KEY, sublime.Region(0, 0), html, sublime.LAYOUT_BLOCK, on_navigate
        )

        # Phantom replacement keeps the viewport, but a shorter document can
        # leave it past the end, so it is reasserted once layout settles.
        sublime.set_timeout(lambda: self._restore(position), 0)

    def _restore(self, position):
        if self.alive() and position[1] > 0:
            self.view.set_viewport_position(position, animate=False)

    def schedule(self):
        """Re-render after a quiet period, coalescing bursts of typing."""
        self.generation += 1
        generation = self.generation

        def fire():
            if self.alive() and generation == self.generation:
                self.render()

        sublime.set_timeout(fire, DEBOUNCE_MS)

    # -- scroll sync -----------------------------------------------------

    def check_resize(self):
        """Re-render when the pane has been resized past a character cell.

        Widths are baked into the markup, so a dragged splitter needs a fresh
        render rather than a reflow. The threshold keeps a drag from queueing a
        render per pixel.
        """
        if not self.alive():
            return
        width = self.view.viewport_extent()[0]
        if width > 0 and abs(width - self.last_width) > 12:
            self.last_width = width
            self.schedule()

    def sync_scroll(self):
        """Scroll the pane to the block matching the editor's first visible line."""
        if not (self.alive() and self.anchors and self.settings.get("scroll_sync", True)):
            return

        visible = self.source.visible_region()
        line, _ = self.source.rowcol(visible.begin())
        if line == self.last_source_line:
            return
        self.last_source_line = line

        fraction = self._anchor_fraction(line)
        extent = self.view.layout_extent()[1]
        viewport = self.view.viewport_extent()[1]
        target = max(0.0, min(fraction * extent, max(0.0, extent - viewport)))
        self.view.set_viewport_position((0.0, target), animate=False)

    def _anchor_fraction(self, line):
        """Map an editor line to a 0..1 position through the document.

        Anchors are the source lines that produced a block, so interpolating
        between the two surrounding anchors tracks the document's real content
        distribution rather than assuming lines are evenly tall.
        """
        anchors = self.anchors
        if line <= anchors[0]:
            return 0.0
        if line >= anchors[-1]:
            return 1.0

        lo = 0
        hi = len(anchors) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if anchors[mid] <= line:
                lo = mid
            else:
                hi = mid

        span = anchors[hi] - anchors[lo]
        within = (line - anchors[lo]) / span if span else 0.0
        return (lo + within) / (len(anchors) - 1)

    # -- lifecycle -------------------------------------------------------

    def alive(self):
        return self.view.is_valid() and self.source.is_valid()

    def close(self):
        if self.view.is_valid():
            self.view.set_scratch(True)
            self.view.close()


# -- module level --------------------------------------------------------


def on_navigate(href):
    """Handle links clicked inside a preview."""
    if href == "markdownx:browser":
        window = sublime.active_window()
        window.run_command("markdownx_preview_browser")
    elif href.startswith(("http://", "https://")):
        import webbrowser

        webbrowser.open(href)


def get(source):
    """Return the live preview for `source`, or None."""
    preview = _previews.get(source.buffer_id())
    if preview and not preview.alive():
        forget(source.buffer_id())
        return None
    return preview


def forget(buffer_id):
    _previews.pop(buffer_id, None)


def all_previews():
    return list(_previews.values())


def open_for(source, settings):
    """Create a preview pane beside `source` and return it."""
    window = source.window()
    if window is None:
        return None

    existing = get(source)
    if existing:
        window.focus_view(existing.view)
        return existing

    # A pane can outlive its registration -- reloading the plugin during
    # development clears the registry while the view stays open. Reclaiming it
    # avoids stacking up duplicate preview tabs.
    _close_orphans(window, source.buffer_id())

    group = _ensure_split(window, source)

    # new_file takes no group argument, so the view is created wherever Sublime
    # puts it and then moved into the preview group.
    view = window.new_file()
    view.set_scratch(True)
    view.set_name("Preview: " + _title(source))
    window.set_view_index(view, group, len(window.views_in_group(group)) - 1)

    view_settings = view.settings()
    view_settings.set(IS_PREVIEW, True)
    view_settings.set(SOURCE_ID, source.buffer_id())
    view_settings.set("gutter", False)
    view_settings.set("line_numbers", False)
    view_settings.set("draw_white_space", "none")
    view_settings.set("draw_indent_guides", False)
    view_settings.set("highlight_line", False)
    view_settings.set("word_wrap", False)
    view_settings.set("scroll_past_end", False)
    view_settings.set("fold_buttons", False)
    view_settings.set("rulers", [])

    preview = Preview(source, view, settings)
    _previews[source.buffer_id()] = preview
    preview.render()

    window.focus_view(source)
    return preview


def _close_orphans(window, buffer_id):
    """Close preview panes for `buffer_id` that no longer have a live Preview."""
    for view in window.views():
        settings = view.settings()
        if settings.get(IS_PREVIEW) and settings.get(SOURCE_ID) == buffer_id:
            view.set_scratch(True)
            view.close()


def _title(source):
    name = source.file_name()
    if name:
        import os

        return os.path.basename(name)
    return source.name() or "Untitled"


def _ensure_split(window, source):
    """Return the group to hold the preview, splitting the window if needed."""
    if window.num_groups() < 2:
        window.run_command("set_layout", {
            "cols": [0.0, 0.5, 1.0],
            "rows": [0.0, 1.0],
            "cells": [[0, 0, 1, 1], [1, 0, 2, 1]],
        })

    source_group = window.get_view_index(source)[0]
    return 1 if source_group == 0 else 0
