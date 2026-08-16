"""Markdown parsing shared by both render targets.

The Sublime pane and the browser tab differ only in how tokens are rendered, so
parsing lives here and each target supplies its own renderer. Two adjustments
are layered on top of stock mistune:

* tokens are stamped with the source line they started on, which scroll sync
  needs and mistune does not record;
* single-line ``$$...$$`` math is recognised, which GitHub accepts and mistune's
  math plugin does not.
"""

import re
from bisect import bisect_right

from .vendor.mistune.block_parser import BlockParser
from .vendor.mistune.core import BlockState
from .vendor.mistune.inline_parser import InlineParser
from .vendor.mistune.markdown import Markdown
from .vendor.mistune.plugins.abbr import abbr
from .vendor.mistune.plugins.def_list import def_list
from .vendor.mistune.plugins.footnotes import footnotes
from .vendor.mistune.plugins.formatting import (
    insert,
    mark,
    strikethrough,
    subscript,
    superscript,
)
from .vendor.mistune.plugins.math import math, math_in_list, math_in_quote
from .vendor.mistune.plugins.table import table
from .vendor.mistune.plugins.task_lists import task_lists
from .vendor.mistune.plugins.url import url

#: GitHub allows ``$$E = mc^2$$`` on a single line; mistune only matches the
#: fenced form with the delimiters on their own lines. The capture group needs a
#: name of its own because mistune compiles every block rule into one combined
#: regex, where a duplicate group name is a compile error.
INLINE_BLOCK_MATH_PATTERN = r"^ {0,3}\$\$[ \t]*(?P<oneline_math_text>[^\n]+?)[ \t]*\$\$[ \t]*$"

#: mistune guards the closing delimiter with ``(?!\s)``, a lookahead that
#: inspects the character *after* the closing ``$`` and so always passes. The
#: effect is that ordinary prose like "it cost $5 and then $6 more" parses as
#: math. This requires non-whitespace on the inside of both delimiters, which is
#: the rule GitHub actually applies, and forbids newlines so a stray ``$``
#: cannot swallow a paragraph.
STRICT_INLINE_MATH_PATTERN = r"\$(?!\s)(?P<math_text>[^$\n]*[^$\s\n])\$"

FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n(?:---|\.\.\.)[ \t]*\n", re.DOTALL)

PLUGINS = (
    table,
    task_lists,
    strikethrough,
    footnotes,
    def_list,
    abbr,
    url,
    mark,
    insert,
    superscript,
    subscript,
    math,
    math_in_quote,
    math_in_list,
)


def _parse_single_line_math(block, m, state):
    state.append_token({"type": "block_math", "raw": m.group("oneline_math_text")})
    return m.end() + 1


def _parse_inline_math(inline, m, state):
    state.append_token({"type": "inline_math", "raw": m.group("math_text")})
    return m.end()


class LineStampedBlockState(BlockState):
    """Records the source line each top-level token began on.

    Scroll sync needs to map a rendered block back to a line in the editor, and
    mistune records no positions. Tokens are stamped with a character offset
    here and resolved to line numbers once parsing finishes.

    Only root-level tokens are stamped: nested states parse a substring, so
    their offsets are relative to that fragment rather than the document, and
    top-level blocks are granular enough to anchor scrolling.
    """

    #: Start offset of the block rule currently being dispatched, set by
    #: LineStampedBlockParser. ``cursor`` is not usable for this because
    #: container blocks such as block quotes parse their children first, which
    #: leaves the cursor at the block's *end* by the time its token is appended.
    rule_start = None

    def append_token(self, token):
        if self.parent is None:
            pos = self.cursor if self.rule_start is None else self.rule_start
            token.setdefault("_pos", pos)
        super().append_token(token)

    def add_paragraph(self, text):
        # Paragraphs bypass append_token entirely, accumulating straight onto
        # `tokens`, so they need stamping here or they carry no line at all.
        # Only the first chunk sets the position; later chunks extend the same
        # paragraph and must not move its start. The cursor is correct here --
        # the parse loop calls this before advancing past the paragraph.
        is_continuation = False
        last = self.last_token()
        if last and last["type"] == "paragraph":
            is_continuation = True

        super().add_paragraph(text)

        if self.parent is None and not is_continuation:
            self.tokens[-1].setdefault("_pos", self.cursor)


class LineStampedBlockParser(BlockParser):
    """Block parser that hands each rule's start offset to the state."""

    state_cls = LineStampedBlockState

    def parse_method(self, m, state):
        outer = state.rule_start
        if state.parent is None:
            state.rule_start = m.start()
        try:
            return super().parse_method(m, state)
        finally:
            state.rule_start = outer


def _resolve_lines(tokens, src):
    """Rewrite the recorded character offsets into 0-based line numbers."""
    starts = [0]
    index = src.find("\n")
    while index != -1:
        starts.append(index + 1)
        index = src.find("\n", index + 1)

    for token in tokens:
        pos = token.pop("_pos", None)
        if pos is not None:
            token["line"] = bisect_right(starts, pos) - 1


def _resolve_lines_hook(md, state):
    """Resolve offsets before rendering, so renderers can read ``line``."""
    _resolve_lines(state.tokens, state.src)


def split_front_matter(text):
    """Return ``(front_matter_or_None, remaining_text, lines_consumed)``."""
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return None, text, 0
    consumed = text[: match.end()].count("\n")
    return match.group(1), text[match.end() :], consumed


def create_parser(renderer):
    """Build a Markdown instance wired to `renderer` with the GFM plugin set."""
    md = Markdown(
        renderer=renderer,
        block=LineStampedBlockParser(),
        inline=InlineParser(),
    )
    for plugin in PLUGINS:
        plugin(md)

    # Registered after the math plugin so it takes precedence for the one-line
    # form; the multi-line pattern requires a newline and cannot be shadowed.
    md.block.register(
        "block_math_inline",
        INLINE_BLOCK_MATH_PATTERN,
        _parse_single_line_math,
        before="list",
    )
    # Re-registering an existing rule name swaps its pattern in place, leaving
    # rule ordering untouched.
    md.inline.register(
        "inline_math",
        STRICT_INLINE_MATH_PATTERN,
        _parse_inline_math,
        before="link",
    )

    # Runs between parsing and rendering, so a renderer sees resolved line
    # numbers rather than raw character offsets.
    md.before_render_hooks.append(_resolve_lines_hook)
    return md


def parse_tokens(text):
    """Parse `text` to a line-stamped token tree without rendering it.

    Returns ``(tokens, front_matter, line_offset)`` where `line_offset` is the
    number of lines the front matter occupied, so callers can map token line
    numbers back to positions in the original document.
    """
    front_matter, body, offset = split_front_matter(text)

    md = create_parser(None)
    tokens, _state = md.parse(body)

    if offset:
        for token in tokens:
            if "line" in token:
                token["line"] += offset

    return tokens, front_matter, offset
