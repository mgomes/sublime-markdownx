"""Vellum -- a live markdown preview for Sublime Text.

Entry point: commands, event listeners, and settings plumbing. Rendering lives
in the ``vellum`` package. The file is named for the plugin rather than matching
the package directory, which would make ``Vellum.vellum`` ambiguous between this
module and that package.
"""

import sublime
import sublime_plugin

from .vellum import code as code_mod
from .vellum import surface

SETTINGS_FILE = "Vellum.sublime-settings"

#: Selector identifying buffers this plugin will preview.
MARKDOWN_SELECTOR = "text.html.markdown, text.html.markdown.multimarkdown, source.gfm"

#: Settings read per render, with the defaults applied when unset.
SETTING_KEYS = (
    "table_max_width",
    "code_max_width",
    "code_line_numbers",
    "scroll_sync",
    "show_front_matter",
    "code_font",
    "body_font",
    "font_size",
    "code_font_size",
)

#: Incremented on every load so a watcher left over from a previous version of
#: this module retires itself instead of running alongside the new one.
_watch_epoch = 0


def plugin_loaded():
    global _watch_epoch
    _watch_epoch += 1
    sublime.set_timeout(lambda: _watch_viewports(_watch_epoch), surface.SYNC_POLL_MS)
    settings().add_on_change("vellum", _on_settings_changed)


def _on_settings_changed():
    """Re-render every open preview so font and layout edits apply at once."""
    for preview in surface.all_previews():
        if preview.alive():
            preview.settings = render_settings(preview.source)
            preview.render()


def plugin_unloaded():
    global _watch_epoch
    _watch_epoch += 1
    settings().clear_on_change("vellum")
    for preview in surface.all_previews():
        preview.close()


def settings():
    return sublime.load_settings(SETTINGS_FILE)


def render_settings(view):
    """Collect the settings a render depends on."""
    stored = settings()
    values = {key: stored.get(key) for key in SETTING_KEYS}
    values = {k: v for k, v in values.items() if v is not None}
    values["tab_size"] = view.settings().get("tab_size", 4)
    return values


def is_markdown(view):
    if not view or not view.is_valid() or view.settings().get(surface.IS_PREVIEW):
        return False
    if view.match_selector(0, MARKDOWN_SELECTOR):
        return True
    name = view.file_name() or ""
    return name.lower().endswith((".md", ".markdown", ".mdown", ".mkd"))


def _watch_viewports(epoch):
    """Poll source viewports so the preview can follow the editor.

    Sublime emits no scroll event, so following it means sampling. Each sample
    is two cheap API calls per open preview that short-circuit unless the first
    visible line actually changed, and there is nothing to do at all when no
    preview is open.
    """
    if epoch != _watch_epoch:
        return

    for preview in surface.all_previews():
        if preview.alive():
            preview.sync_scroll()
            preview.check_resize()
        else:
            surface.forget(preview.source.buffer_id())

    sublime.set_timeout(lambda: _watch_viewports(epoch), surface.SYNC_POLL_MS)


class VellumPreviewCommand(sublime_plugin.TextCommand):
    """Toggle the in-editor preview pane for the current markdown file."""

    def run(self, edit):
        existing = surface.get(self.view)
        if existing:
            existing.close()
            surface.forget(self.view.buffer_id())
            return

        surface.open_for(self.view, render_settings(self.view))

    def is_enabled(self):
        return is_markdown(self.view)

    def is_visible(self):
        return is_markdown(self.view)


class VellumRefreshCommand(sublime_plugin.TextCommand):
    """Force a re-render, discarding cached syntax lookups."""

    def run(self, edit):
        code_mod.clear_cache(self.view.window())
        preview = surface.get(self.view)
        if preview:
            preview.settings = render_settings(self.view)
            preview.render()

    def is_enabled(self):
        return surface.get(self.view) is not None


class VellumEventListener(sublime_plugin.EventListener):
    def on_modified_async(self, view):
        preview = surface.get(view)
        if preview:
            preview.schedule()

    def on_post_save_async(self, view):
        preview = surface.get(view)
        if preview:
            preview.render()

    def on_pre_close(self, view):
        preview = surface.get(view)
        if preview:
            preview.close()
            surface.forget(view.buffer_id())
            return

        # Closing the preview pane itself unregisters the pairing.
        if view.settings().get(surface.IS_PREVIEW):
            surface.forget(view.settings().get(surface.SOURCE_ID))

    def on_load_async(self, view):
        if is_markdown(view) and settings().get("auto_open", False):
            surface.open_for(view, render_settings(view))
