"""Renders parsed markdown into minihtml for the in-editor preview pane.

minihtml is a small subset of HTML: no ``<table>``, no ``<pre>``, no
``<blockquote>`` styling beyond what CSS gives a ``<div>``, and no JavaScript.
The interesting work here is therefore substitution -- expressing constructs
with the tags that do exist -- rather than markup generation.

Blocks carry a ``data-line`` style anchor through the ``id`` attribute so the
pane can be scrolled to match the editor.
"""

import os

from . import code as code_mod
from . import tables
from .vendor.mistune.core import BaseRenderer

#: Fences the browser target renders and this one cannot.
RICH_FENCES = {
    "mermaid": "Mermaid diagram",
    "math": "Math block",
    "katex": "Math block",
    "latex": "Math block",
}

ESCAPES = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
)


def escape(text):
    for char, entity in ESCAPES:
        text = text.replace(char, entity)
    return text


def spaces(text):
    """Escape `text` and make its spacing literal.

    minihtml collapses runs of whitespace like a browser, so padded table cells
    and indented code would lose their shape without this.
    """
    return escape(text).replace(" ", "&nbsp;")


class MiniHtmlRenderer(BaseRenderer):
    """Token renderer targeting Sublime's minihtml."""

    NAME = "minihtml"

    def __init__(self, window, base_dir=None, settings=None):
        super().__init__()
        self.window = window
        self.base_dir = base_dir
        self.settings = settings or {}
        self.tab_size = self.settings.get("tab_size", 4)
        self.table_width = self.settings.get("table_max_width", 100)
        self.show_line_numbers = self.settings.get("code_line_numbers", False)
        self.anchors = []

    # -- helpers ---------------------------------------------------------

    def _anchor(self, token):
        """Return an id attribute recording the token's source line."""
        line = token.get("line")
        if line is None:
            return ""
        self.anchors.append(line)
        return ' id="L%d"' % line

    def _resolve(self, url):
        """Turn a document-relative image path into something minihtml loads."""
        if not url:
            return url
        lowered = url.lower()
        if lowered.startswith(("http://", "https://", "data:", "file://", "res://")):
            return url
        if self.base_dir and not os.path.isabs(url):
            return "file://" + os.path.normpath(os.path.join(self.base_dir, url))
        if os.path.isabs(url):
            return "file://" + url
        return url

    # -- inline tokens ---------------------------------------------------

    def text(self, token, state):
        return escape(token["raw"])

    def emphasis(self, token, state):
        return "<i>%s</i>" % self.render_tokens(token["children"], state)

    def strong(self, token, state):
        return "<b>%s</b>" % self.render_tokens(token["children"], state)

    def link(self, token, state):
        attrs = token.get("attrs", {})
        text = self.render_tokens(token["children"], state) if token.get("children") else escape(attrs.get("url", ""))
        return '<a href="%s">%s</a>' % (escape(attrs.get("url", "")), text)

    def image(self, token, state):
        attrs = token.get("attrs", {})
        return '<img src="%s">' % escape(self._resolve(attrs.get("url", "")))

    def codespan(self, token, state):
        # Thin spaces pad the background box; minihtml ignores horizontal
        # padding on inline elements.
        return "<code>&nbsp;%s&nbsp;</code>" % spaces(token["raw"])

    def linebreak(self, token, state):
        return "<br>"

    def softbreak(self, token, state):
        return " "

    def inline_html(self, token, state):
        return escape(token["raw"])

    def strikethrough(self, token, state):
        return "<del>%s</del>" % self.render_tokens(token["children"], state)

    def mark(self, token, state):
        return "<mark>%s</mark>" % self.render_tokens(token["children"], state)

    def insert(self, token, state):
        return "<u>%s</u>" % self.render_tokens(token["children"], state)

    def superscript(self, token, state):
        return "<span>^%s</span>" % self.render_tokens(token["children"], state)

    def subscript(self, token, state):
        return "<span>_%s</span>" % self.render_tokens(token["children"], state)

    def inline_math(self, token, state):
        return '<code>&nbsp;%s&nbsp;</code>' % spaces(token["raw"])

    def abbr(self, token, state):
        return self.render_tokens(token["children"], state)

    # -- block tokens ----------------------------------------------------

    def paragraph(self, token, state):
        return "<p%s>%s</p>" % (self._anchor(token), self.render_tokens(token["children"], state))

    def heading(self, token, state):
        level = token["attrs"]["level"]
        return "<h%d%s>%s</h%d>" % (
            level,
            self._anchor(token),
            self.render_tokens(token["children"], state),
            level,
        )

    def thematic_break(self, token, state):
        return '<div class="hr"></div>'

    def blank_line(self, token, state):
        return ""

    def block_text(self, token, state):
        return self.render_tokens(token["children"], state)

    def block_html(self, token, state):
        # Raw HTML is shown rather than interpreted: minihtml would silently
        # drop most of it, and a visible block is more useful than a blank gap.
        return '<div class="code">%s</div>' % self._code_lines(escape(token["raw"]).split("\n"))

    def block_quote(self, token, state):
        return "<blockquote%s>%s</blockquote>" % (
            self._anchor(token),
            self.render_tokens(token["children"], state),
        )

    def block_error(self, token, state):
        return '<div class="note">%s</div>' % escape(token.get("raw", "parse error"))

    def block_math(self, token, state):
        return self._placeholder("Math block", token.get("raw", ""), token)

    def block_code(self, token, state):
        info = token.get("attrs", {}).get("info") or ""
        lang = code_mod.normalize_info(info)
        raw = token["raw"]

        if lang in RICH_FENCES:
            return self._placeholder(RICH_FENCES[lang], raw, token)

        html, syntax_name = code_mod.highlight(self.window, raw, info, self.tab_size)
        lines = code_mod.split_lines(html)

        label = ""
        if syntax_name and syntax_name != "Plain Text":
            label = '<div class="code-lang">%s</div>' % escape(syntax_name)

        return '<div class="code"%s>%s%s</div>' % (
            self._anchor(token),
            label,
            self._code_lines(lines, pre_rendered=True),
        )

    def _code_lines(self, lines, pre_rendered=False):
        """Join code lines, optionally numbering them in a padded gutter."""
        if not pre_rendered:
            lines = [spaces(line) for line in lines]

        if not self.show_line_numbers:
            return "<br>".join(lines)

        width = len(str(len(lines)))
        numbered = []
        for index, line in enumerate(lines, 1):
            gutter = str(index).rjust(width).replace(" ", "&nbsp;")
            numbered.append('<span class="ln">%s&nbsp;&nbsp;</span>%s' % (gutter, line))
        return "<br>".join(numbered)

    def _placeholder(self, kind, raw, token):
        """A card standing in for content only the browser target can render."""
        first = (raw.strip().split("\n") or [""])[0]
        return (
            '<div class="note"%s>'
            '<span class="note-title">%s</span><br>'
            "<code>&nbsp;%s&nbsp;</code><br>"
            '<span class="note-hint">Not renderable in Sublime -- </span>'
            '<a href="vellum:browser">open preview in browser</a>'
            "</div>"
        ) % (self._anchor(token), escape(kind), spaces(first[:80]))

    # -- lists -----------------------------------------------------------

    def list(self, token, state):
        attrs = token.get("attrs", {})
        tag = "ol" if attrs.get("ordered") else "ul"
        cls = ' class="tight"' if token.get("tight") else ""
        return "<%s%s%s>%s</%s>" % (
            tag,
            cls,
            self._anchor(token),
            self.render_tokens(token["children"], state),
            tag,
        )

    def list_item(self, token, state):
        return "<li>%s</li>" % self.render_tokens(token["children"], state)

    def task_list_item(self, token, state):
        checked = token.get("attrs", {}).get("checked")
        box = (
            '<span class="task">[x]</span>' if checked else '<span class="task-open">[&nbsp;]</span>'
        )
        return "<li>%s&nbsp;%s</li>" % (box, self.render_tokens(token["children"], state))

    # -- definition lists ------------------------------------------------

    def def_list(self, token, state):
        return "<div%s>%s</div>" % (self._anchor(token), self.render_tokens(token["children"], state))

    def def_list_head(self, token, state):
        return "<p><b>%s</b></p>" % self.render_tokens(token["children"], state)

    def def_list_item(self, token, state):
        return "<blockquote>%s</blockquote>" % self.render_tokens(token["children"], state)

    # -- footnotes -------------------------------------------------------

    def footnote_ref(self, token, state):
        index = token.get("attrs", {}).get("index", "?")
        return '<a href="#fn%s">[%s]</a>' % (index, index)

    def footnotes(self, token, state):
        return '<div class="footnotes">%s</div>' % self.render_tokens(token["children"], state)

    def footnote_item(self, token, state):
        index = token.get("attrs", {}).get("index", "?")
        return '<p id="fn%s">[%s] %s</p>' % (
            index,
            index,
            self.render_tokens(token["children"], state),
        )

    # -- tables ----------------------------------------------------------

    def table(self, token, state):
        """Lay the table out as padded monospace rows.

        Cell text has to be measured before it is marked up, so each cell is
        rendered twice: once plain to size the column, once with inline markup
        for display. Padding is appended around the marked-up version.
        """
        head_rows, body_rows, aligns = [], [], []

        for section in token["children"]:
            for row in self._rows_of(section):
                plain, rich = [], []
                for cell in row["children"]:
                    plain.append(self._plain_text(cell))
                    rich.append(self.render_tokens(cell["children"], state))
                    if section["type"] == "table_head":
                        aligns.append(cell.get("attrs", {}).get("align"))
                target = head_rows if section["type"] == "table_head" else body_rows
                target.append((plain, rich))

        measured = [plain for plain, _ in head_rows + body_rows]
        widths = tables.solve_widths(measured, self.table_width)

        out = []
        for index, (plain, rich) in enumerate(head_rows):
            out.append('<div class="th">%s</div>' % self._cells(plain, rich, widths, aligns))
        for index, (plain, rich) in enumerate(body_rows):
            cls = "tr odd" if index % 2 else "tr"
            out.append('<div class="%s">%s</div>' % (cls, self._cells(plain, rich, widths, aligns)))

        return '<div class="table"%s>%s</div>' % (self._anchor(token), "".join(out))

    def _cells(self, plain, rich, widths, aligns):
        """Pad each rendered cell to its column width and join with a gutter."""
        out = []
        for index, width in enumerate(widths):
            raw = plain[index] if index < len(plain) else ""
            markup = rich[index] if index < len(rich) else ""
            align = aligns[index] if index < len(aligns) else None

            clipped = tables.truncate(raw, width)
            if clipped != raw:
                # Truncation invalidates the inline markup, so fall back to text.
                markup = escape(clipped)

            slack = width - tables.text_width(clipped)
            lead, trail = self._slack(slack, align)
            out.append("&nbsp;" * (lead + tables.GUTTER) + markup + "&nbsp;" * (trail + tables.GUTTER))
        return "".join(out)

    @staticmethod
    def _slack(slack, align):
        if slack <= 0:
            return 0, 0
        if align == "right":
            return slack, 0
        if align == "center":
            left = slack // 2
            return left, slack - left
        return 0, slack

    @staticmethod
    def _rows_of(section):
        if section["type"] == "table_head":
            return [{"children": section["children"]}]
        return section["children"]

    def _plain_text(self, token):
        """Flatten a token subtree to its visible text, for measurement."""
        if "raw" in token and not token.get("children"):
            return token["raw"]
        out = []
        for child in token.get("children", []):
            out.append(self._plain_text(child))
        return "".join(out)
