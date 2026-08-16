"""Preview styling derived from the active colour scheme.

The preview should look like it belongs in the editor, so rather than shipping a
palette it reads the user's scheme through ``View.style()`` and mixes the few
extra tones a document needs -- code block backgrounds, table rules, zebra
striping -- from the colours already there.

minihtml supports no ``width`` or ``max-width``, so nothing here sizes anything;
blocks fill the pane and text wraps at its edge.
"""

#: Fallbacks for schemes that leave a key unset. Values are Mariana's, which is
#: a middling dark scheme and so degrades reasonably in either direction.
DEFAULTS = {
    "background": "#303841",
    "foreground": "#d8dee9",
    "accent": "#5c99d6",
    "bluish": "#6699cc",
    "redish": "#ec5f66",
    "greenish": "#99c794",
    "orangish": "#f9ae58",
    "guide": "#49505a",
    "shadow": "#232930",
}


#: Appended to whatever family the user asks for. "system" is Sublime's UI
#: font; the generics behind it catch the case where even that fails.
BODY_FALLBACKS = ("system", "Helvetica Neue", "sans-serif")
CODE_FALLBACKS = ("Menlo", "Consolas", "monospace")


def _stack(preferred, fallbacks):
    """Build a font-family stack, putting `preferred` first if it is set.

    Names are never quoted. Unlike CSS proper, minihtml fails to parse a quoted
    family -- even one containing spaces -- and renders nothing at all, so
    ``Helvetica Neue`` has to be written bare.
    """
    names = [preferred] if preferred else []
    names.extend(name for name in fallbacks if name != preferred)
    return ", ".join(name.replace(",", " ").strip() for name in names)


def parse_hex(value, fallback="#000000"):
    """Parse ``#rgb``/``#rrggbb``/``#rrggbbaa`` into an ``(r, g, b)`` triple."""
    if not isinstance(value, str) or not value.startswith("#"):
        value = fallback

    digits = value[1:]
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    if len(digits) < 6:
        digits = fallback[1:]

    try:
        return tuple(int(digits[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return parse_hex(fallback)


def to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def blend(a, b, ratio):
    """Mix `ratio` of colour `a` into colour `b`."""
    ca, cb = parse_hex(a), parse_hex(b)
    return to_hex([ca[i] * ratio + cb[i] * (1 - ratio) for i in range(3)])


def luminance(value):
    r, g, b = parse_hex(value)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


class Theme:
    """Colours and fonts for one render, derived from a view's scheme."""

    def __init__(self, view, settings=None):
        settings = settings or {}
        style = view.style() or {}

        def scheme(key):
            return style.get(key) or DEFAULTS[key]

        def scope_fg(scope, fallback):
            info = view.style_for_scope(scope) or {}
            return info.get("foreground") or fallback

        self.bg = scheme("background")
        self.fg = scheme("foreground")
        self.accent = scheme("accent")
        self.dark = luminance(self.bg) < 0.5

        self.link = scope_fg("markup.underline.link", scheme("bluish"))
        self.muted = scope_fg("comment", blend(self.fg, self.bg, 0.55))

        # Surfaces. A dark scheme reads better with code sunk below the page and
        # a light one with it raised, so the mix direction follows the scheme.
        contrast = self.fg if not self.dark else "#000000"
        self.code_bg = blend(contrast, self.bg, 0.06 if self.dark else 0.04)
        self.border = style.get("guide") or blend(self.fg, self.bg, 0.25)
        self.rule = blend(self.fg, self.bg, 0.35)
        self.stripe = blend(self.fg, self.bg, 0.06)
        self.header_bg = blend(self.fg, self.bg, 0.14)

        self.quote_border = blend(self.accent, self.bg, 0.7)
        self.checked = scope_fg("markup.inserted", scheme("greenish"))
        self.warn_bg = blend(scheme("orangish"), self.bg, 0.12)
        self.warn_border = blend(scheme("orangish"), self.bg, 0.45)

        view_settings = view.settings()

        # Both faces are configurable. Code follows the editor's font by default
        # so fences look identical in both panes; body text uses the UI face,
        # since proportional type reads better for prose.
        #
        # Each is emitted as a stack. minihtml honours comma-separated families
        # and falls through correctly, but a single unresolvable name lands on
        # Times New Roman -- so a typo in this setting would otherwise silently
        # turn the whole preview serif.
        self.code_font = _stack(
            settings.get("code_font") or view_settings.get("font_face"),
            CODE_FALLBACKS,
        )
        self.body_font = _stack(settings.get("body_font"), BODY_FALLBACKS)

        editor_size = view_settings.get("font_size") or 12
        # Proportional text reads smaller than monospace at equal size, so the
        # body is nudged up a point unless told otherwise.
        self.size = int(settings.get("font_size") or (editor_size + 1))
        self.code_size = int(settings.get("code_font_size") or max(9, round(self.size * 0.92)))

    def css(self):
        """Return the stylesheet for a preview document."""
        s = self.size
        return CSS_TEMPLATE.format(
            bg=self.bg,
            fg=self.fg,
            muted=self.muted,
            link=self.link,
            accent=self.accent,
            border=self.border,
            rule=self.rule,
            stripe=self.stripe,
            header_bg=self.header_bg,
            code_bg=self.code_bg,
            quote_border=self.quote_border,
            checked=self.checked,
            warn_bg=self.warn_bg,
            warn_border=self.warn_border,
            code_font=self.code_font,
            body_font=self.body_font,
            s=s,
            h1=int(s * 1.9),
            h2=int(s * 1.55),
            h3=int(s * 1.3),
            h4=int(s * 1.12),
            small=max(9, int(s * 0.85)),
            code_size=self.code_size,
        )


CSS_TEMPLATE = """
body {{
    margin: 0;
    padding: 0;
    background-color: {bg};
    color: {fg};
    font-family: {body_font};
    font-size: {s}px;
    line-height: 1.6;
}}

/* A block phantom sizes itself to its content and never wraps, so a long
   paragraph would run off the pane instead of reflowing. Giving the page an
   explicit pixel width restores wrapping. `width` is absent from the documented
   minihtml property list but is honoured -- verified against build 4200. */
.page {{ padding: {s}px {s}px {s}px {s}px; }}

a {{ color: {link}; text-decoration: none; }}

h1, h2, h3, h4, h5, h6 {{
    font-weight: bold;
    line-height: 1.25;
    margin-top: {s}px;
    margin-bottom: 6px;
}}
h1 {{ font-size: {h1}px; border-bottom: 2px solid {rule}; padding-bottom: 5px; }}
h2 {{ font-size: {h2}px; border-bottom: 1px solid {rule}; padding-bottom: 4px; }}
h3 {{ font-size: {h3}px; }}
h4 {{ font-size: {h4}px; }}
h5, h6 {{ font-size: {s}px; color: {muted}; }}

p {{ margin-top: 0; margin-bottom: {s}px; }}

ul {{ margin-top: 0; margin-bottom: {s}px; padding-left: {s}px; list-style-type: disc; }}
/* minihtml defaults <ol> to bullets, so numbering has to be asked for. */
ol {{ margin-top: 0; margin-bottom: {s}px; padding-left: {s}px; list-style-type: decimal; }}
ul ul {{ list-style-type: circle; }}
ul ul ul {{ list-style-type: square; }}
/* Ordered lists are divs, not <ol>: minihtml draws a bullet for <ol> and
   ignores list-style-type, so there is no way to suppress it on a real list. */
.ord {{ margin-bottom: {s}px; }}
.ord-item {{ padding-left: {s}px; margin-bottom: 3px; }}
.tight .ord-item {{ margin-bottom: 0; }}
.num {{ color: {muted}; font-family: {code_font}; }}
li {{ margin-bottom: 3px; }}
.tight li {{ margin-bottom: 0; }}
.tight {{ margin-bottom: {s}px; }}

.hr {{
    border-bottom: 1px solid {rule};
    margin-top: {s}px;
    margin-bottom: {s}px;
}}

/* Inline code. No padding-x on inline elements in minihtml, so the background
   is nudged out with thin spaces instead. */
code {{
    font-family: {code_font};
    font-size: {code_size}px;
    background-color: {code_bg};
    color: {fg};
}}

.code {{
    background-color: {code_bg};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 8px 10px 8px 10px;
    margin-bottom: {s}px;
    font-family: {code_font};
    font-size: {code_size}px;
    line-height: 1.45;
}}
.code-lang {{
    color: {muted};
    font-family: {body_font};
    font-size: {small}px;
}}
.ln {{ color: {muted}; }}

blockquote {{
    border-left: 3px solid {quote_border};
    padding-left: 10px;
    margin-top: 0;
    margin-bottom: {s}px;
    color: {muted};
}}

/* Tables are rows of padded monospace text: minihtml has no table layout. */
.table {{
    font-family: {code_font};
    font-size: {code_size}px;
    line-height: 1.5;
    margin-bottom: {s}px;
    border: 1px solid {border};
    border-radius: 4px;
}}
.tr {{ padding-left: 6px; padding-right: 6px; }}
.th {{
    font-weight: bold;
    background-color: {header_bg};
    border-bottom: 1px solid {border};
    padding-left: 6px;
    padding-right: 6px;
}}
.odd {{ background-color: {stripe}; }}

.task {{ color: {checked}; font-family: {code_font}; }}
.task-open {{ color: {muted}; font-family: {code_font}; }}

.note {{
    background-color: {warn_bg};
    border: 1px solid {warn_border};
    border-radius: 4px;
    padding: 8px 10px 8px 10px;
    margin-bottom: {s}px;
    color: {fg};
}}
.note-title {{ font-weight: bold; }}
.note-hint {{ color: {muted}; font-size: {small}px; }}

.fm {{
    background-color: {code_bg};
    border-left: 3px solid {border};
    padding: 6px 10px 6px 10px;
    margin-bottom: {s}px;
    color: {muted};
    font-family: {code_font};
    font-size: {small}px;
}}

.footnotes {{
    border-top: 1px solid {rule};
    margin-top: {s}px;
    padding-top: 6px;
    color: {muted};
    font-size: {small}px;
}}

.math {{ font-family: {code_font}; color: {muted}; }}
del {{ color: {muted}; }}
mark {{ background-color: {warn_bg}; color: {fg}; }}
"""
