"""Assembles a complete minihtml document for the preview pane."""

import os

from .parse import create_parser, split_front_matter
from .render_mini import MiniHtmlRenderer, escape, spaces
from .theme import Theme


def _front_matter_block(text, show):
    if not text or not show:
        return ""
    lines = [spaces(line) for line in text.strip().split("\n")]
    return '<div class="fm">%s</div>' % "<br>".join(lines)


def render(view, text, settings=None):
    """Render `text` to a minihtml document styled for `view`'s colour scheme.

    Returns ``(html, anchors)`` where `anchors` is the sorted list of source
    lines that produced an addressable block, used to align scrolling.
    """
    settings = settings or {}
    window = view.window()
    file_name = view.file_name()
    base_dir = os.path.dirname(file_name) if file_name else None

    front_matter, body, offset = split_front_matter(text)

    renderer = MiniHtmlRenderer(window, base_dir=base_dir, settings=settings)
    md = create_parser(renderer)
    html, state = md.parse(body)

    theme = Theme(view, settings)
    document = (
        "<body id=vellum>"
        "<style>%s</style>"
        "%s%s"
        "</body>"
    ) % (
        theme.css(),
        _front_matter_block(front_matter, settings.get("show_front_matter", True)),
        html,
    )

    anchors = sorted({line + offset for line in renderer.anchors})
    return document, anchors


def render_error(view, message, detail=""):
    """Render a failure as a styled card rather than leaving a blank pane."""
    theme = Theme(view)
    body = '<span class="note-title">Preview failed</span><br>%s' % escape(message)
    if detail:
        body += '<br><br><span class="note-hint">%s</span>' % spaces(detail)
    return '<body id=vellum><style>%s</style><div class="note">%s</div></body>' % (
        theme.css(),
        body,
    )
