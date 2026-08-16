"""Renders parsed markdown to ordinary HTML for the browser target.

This renderer has none of the Sublime pane's constraints: real ``<table>``,
``<pre>``, and a JavaScript engine. Highlighting, diagrams and math are all
deferred to the page, which loads highlight.js, Mermaid and KaTeX from the
plugin's own vendored copies.

Blocks carry ``data-line`` so the page can scroll in step with the editor.
"""

from urllib.parse import quote

from .util import escape, escape_attr, slugify
from .vendor.mistune.core import BaseRenderer

#: Fences handled by a client-side library instead of the highlighter.
MERMAID_INFO = ("mermaid",)


class WebRenderer(BaseRenderer):
    """Token renderer producing standards HTML."""

    NAME = "web"

    def __init__(self, base_url="", asset_query="", settings=None):
        super().__init__()
        self.base_url = base_url
        self.asset_query = asset_query
        self.settings = settings or {}
        self.headings = []
        self.uses_mermaid = False
        self.uses_math = False

    # -- helpers ---------------------------------------------------------

    def _anchor(self, token):
        line = token.get("line")
        return ' data-line="%d"' % line if line is not None else ""

    def _resolve(self, url):
        """Rewrite a document-relative URL to load through the local server.

        The file route is token-guarded like every other, so the auth query has
        to ride along on each asset URL.
        """
        if not url:
            return url
        lowered = url.lower()
        if lowered.startswith(("http://", "https://", "data:", "mailto:", "#")):
            return url
        if not self.base_url:
            return url

        path, _, fragment = url.partition("#")
        resolved = self.base_url + quote(path.lstrip("/")) + self.asset_query
        return resolved + ("#" + fragment if fragment else "")

    # -- inline ----------------------------------------------------------

    def text(self, token, state):
        return escape(token["raw"])

    def emphasis(self, token, state):
        return "<em>%s</em>" % self.render_tokens(token["children"], state)

    def strong(self, token, state):
        return "<strong>%s</strong>" % self.render_tokens(token["children"], state)

    def link(self, token, state):
        url = token.get("attrs", {}).get("url", "")
        body = self.render_tokens(token["children"], state) if token.get("children") else escape(url)
        external = url.lower().startswith(("http://", "https://"))
        extra = ' target="_blank" rel="noreferrer noopener"' if external else ""
        return '<a href="%s"%s>%s</a>' % (escape_attr(self._resolve(url)), extra, body)

    def image(self, token, state):
        attrs = token.get("attrs", {})
        alt = self.render_tokens(token["children"], state) if token.get("children") else ""
        title = attrs.get("title")
        extra = ' title="%s"' % escape_attr(title) if title else ""
        return '<img src="%s" alt="%s"%s loading="lazy">' % (
            escape_attr(self._resolve(attrs.get("url", ""))),
            escape_attr(alt),
            extra,
        )

    def codespan(self, token, state):
        return "<code>%s</code>" % escape(token["raw"])

    def linebreak(self, token, state):
        return "<br>\n"

    def softbreak(self, token, state):
        return "\n"

    def inline_html(self, token, state):
        return token["raw"]

    def strikethrough(self, token, state):
        return "<del>%s</del>" % self.render_tokens(token["children"], state)

    def mark(self, token, state):
        return "<mark>%s</mark>" % self.render_tokens(token["children"], state)

    def insert(self, token, state):
        return "<ins>%s</ins>" % self.render_tokens(token["children"], state)

    def superscript(self, token, state):
        return "<sup>%s</sup>" % self.render_tokens(token["children"], state)

    def subscript(self, token, state):
        return "<sub>%s</sub>" % self.render_tokens(token["children"], state)

    def abbr(self, token, state):
        title = token.get("attrs", {}).get("title", "")
        return '<abbr title="%s">%s</abbr>' % (
            escape_attr(title),
            self.render_tokens(token["children"], state),
        )

    def inline_math(self, token, state):
        self.uses_math = True
        return '<span class="math-inline">%s</span>' % escape(token["raw"])

    # -- blocks ----------------------------------------------------------

    def paragraph(self, token, state):
        return "<p%s>%s</p>\n" % (self._anchor(token), self.render_tokens(token["children"], state))

    def heading(self, token, state):
        level = token["attrs"]["level"]
        body = self.render_tokens(token["children"], state)
        slug = slugify(_plain_text(token))
        self.headings.append((level, _plain_text(token), slug))
        return '<h%d id="%s"%s>%s<a class="anchor" href="#%s">#</a></h%d>\n' % (
            level,
            escape_attr(slug),
            self._anchor(token),
            body,
            escape_attr(slug),
            level,
        )

    def thematic_break(self, token, state):
        return "<hr>\n"

    def blank_line(self, token, state):
        return ""

    def block_text(self, token, state):
        return self.render_tokens(token["children"], state)

    def block_html(self, token, state):
        return token["raw"]

    def block_quote(self, token, state):
        return "<blockquote%s>\n%s</blockquote>\n" % (
            self._anchor(token),
            self.render_tokens(token["children"], state),
        )

    def block_error(self, token, state):
        return '<div class="error">%s</div>\n' % escape(token.get("raw", "parse error"))

    def block_math(self, token, state):
        self.uses_math = True
        return '<div class="math-block"%s>%s</div>\n' % (
            self._anchor(token),
            escape(token.get("raw", "")),
        )

    def block_code(self, token, state):
        info = (token.get("attrs", {}).get("info") or "").strip()
        lang = info.split()[0].lower() if info else ""
        raw = token["raw"].rstrip("\n")

        if lang in MERMAID_INFO:
            self.uses_mermaid = True
            return '<div class="mermaid"%s>%s</div>\n' % (self._anchor(token), escape(raw))

        cls = ' class="language-%s"' % escape_attr(lang) if lang else ""
        label = '<span class="code-lang">%s</span>' % escape(lang) if lang else ""
        return (
            '<div class="code-block"%s>%s'
            '<button class="copy" type="button">Copy</button>'
            "<pre><code%s>%s</code></pre></div>\n"
        ) % (self._anchor(token), label, cls, escape(raw))

    # -- lists -----------------------------------------------------------

    def list(self, token, state):
        attrs = token.get("attrs", {})
        ordered = attrs.get("ordered")
        tag = "ol" if ordered else "ul"
        start = attrs.get("start")
        extra = ' start="%d"' % int(start) if ordered and start else ""
        cls = ' class="tight"' if token.get("tight") else ""
        return "<%s%s%s%s>\n%s</%s>\n" % (
            tag,
            extra,
            cls,
            self._anchor(token),
            self.render_tokens(token["children"], state),
            tag,
        )

    def list_item(self, token, state):
        return "<li>%s</li>\n" % self.render_tokens(token["children"], state)

    def task_list_item(self, token, state):
        checked = token.get("attrs", {}).get("checked")
        box = '<input type="checkbox" disabled%s>' % (" checked" if checked else "")
        return '<li class="task">%s%s</li>\n' % (box, self.render_tokens(token["children"], state))

    # -- definition lists ------------------------------------------------

    def def_list(self, token, state):
        return "<dl%s>\n%s</dl>\n" % (self._anchor(token), self.render_tokens(token["children"], state))

    def def_list_head(self, token, state):
        return "<dt>%s</dt>\n" % self.render_tokens(token["children"], state)

    def def_list_item(self, token, state):
        return "<dd>%s</dd>\n" % self.render_tokens(token["children"], state)

    # -- footnotes -------------------------------------------------------

    def footnote_ref(self, token, state):
        index = token.get("attrs", {}).get("index", "?")
        return '<sup class="fn-ref"><a href="#fn-%s" id="fnref-%s">%s</a></sup>' % (
            index,
            index,
            index,
        )

    def footnotes(self, token, state):
        return '<section class="footnotes"><hr>\n<ol>\n%s</ol></section>\n' % self.render_tokens(
            token["children"], state
        )

    def footnote_item(self, token, state):
        index = token.get("attrs", {}).get("index", "?")
        return '<li id="fn-%s">%s<a class="fn-back" href="#fnref-%s">&#8617;</a></li>\n' % (
            index,
            self.render_tokens(token["children"], state),
            index,
        )

    # -- tables ----------------------------------------------------------

    def table(self, token, state):
        return '<div class="table-wrap"%s><table>\n%s</table></div>\n' % (
            self._anchor(token),
            self.render_tokens(token["children"], state),
        )

    def table_head(self, token, state):
        return "<thead><tr>\n%s</tr></thead>\n" % self.render_tokens(token["children"], state)

    def table_body(self, token, state):
        return "<tbody>\n%s</tbody>\n" % self.render_tokens(token["children"], state)

    def table_row(self, token, state):
        return "<tr>\n%s</tr>\n" % self.render_tokens(token["children"], state)

    def table_cell(self, token, state):
        attrs = token.get("attrs", {})
        tag = "th" if attrs.get("head") else "td"
        align = attrs.get("align")
        style = ' style="text-align:%s"' % align if align else ""
        return "<%s%s>%s</%s>\n" % (tag, style, self.render_tokens(token["children"], state), tag)


def _plain_text(token):
    """Flatten a token subtree to its visible text."""
    if "raw" in token and not token.get("children"):
        return token["raw"]
    return "".join(_plain_text(child) for child in token.get("children", []))
