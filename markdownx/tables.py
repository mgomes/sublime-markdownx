"""Column layout for tables rendered without a ``<table>`` tag.

minihtml implements no table layout, so the Sublime target draws tables as rows
of padded text in the editor's monospace font. Padding is measured in character
cells rather than pixels: CSS length units do not correspond to a font's advance
width, so a width-based approach drifts out of alignment as soon as the font
changes.

This module is pure text measurement with no Sublime dependency, so it is
covered by the offline tests.
"""

import unicodedata

#: Cell padding, in character cells, applied either side of every column.
GUTTER = 1

#: Columns narrower than this are never chosen as the victim when a table has to
#: be shrunk to fit; squeezing them produces unreadable stacks of one character.
MIN_COLUMN = 5


def char_width(char):
    """Width of `char` in terminal-style character cells.

    East Asian wide and fullwidth forms occupy two cells; combining marks
    occupy none. Everything else counts as one.
    """
    if unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def text_width(text):
    """Display width of `text` in character cells."""
    return sum(char_width(c) for c in text)


def truncate(text, width):
    """Clip `text` to `width` cells, ending with an ellipsis when it does not fit."""
    if text_width(text) <= width:
        return text
    if width <= 0:
        return ""
    if width == 1:
        return "…"

    out = []
    used = 0
    for char in text:
        size = char_width(char)
        if used + size > width - 1:
            break
        out.append(char)
        used += size
    return "".join(out) + "…"


def solve_widths(rows, max_total=None):
    """Return the display width to allot each column.

    `rows` is a list of rows, each a list of cell strings. Columns start at
    their natural width -- the widest cell they contain -- and are then shrunk
    to satisfy `max_total` if one is given.

    Shrinking repeatedly takes a cell off whichever column is currently widest,
    so a single runaway column absorbs the loss instead of every column being
    squeezed evenly. Columns already at ``MIN_COLUMN`` are left alone, which
    means an impossible budget yields the narrowest achievable table rather than
    an error.
    """
    if not rows:
        return []

    count = max(len(row) for row in rows)
    widths = [0] * count
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], text_width(cell))

    if max_total is None:
        return widths

    budget = max_total - (2 * GUTTER * count)
    while sum(widths) > budget:
        widest = max(range(count), key=lambda i: widths[i])
        if widths[widest] <= MIN_COLUMN:
            break
        widths[widest] -= 1

    return widths


def pad(text, width, align):
    """Pad `text` to `width` cells according to `align`.

    Returns the text unchanged if it is already wider than `width`; callers
    truncate first when they need a hard bound.
    """
    slack = width - text_width(text)
    if slack <= 0:
        return text

    if align == "right":
        return " " * slack + text
    if align == "center":
        left = slack // 2
        return " " * left + text + " " * (slack - left)
    return text + " " * slack


def layout(rows, aligns, max_total=None):
    """Lay `rows` out into equal-width columns.

    Returns a list of rows of padded cell strings, every row the same shape.
    Cells too wide for their column are truncated with an ellipsis.
    """
    widths = solve_widths(rows, max_total)
    count = len(widths)

    laid_out = []
    for row in rows:
        cells = []
        for index in range(count):
            raw = row[index] if index < len(row) else ""
            align = aligns[index] if index < len(aligns) else None
            cells.append(pad(truncate(raw, widths[index]), widths[index], align))
        laid_out.append(cells)

    return laid_out
