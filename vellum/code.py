"""Syntax highlighting for fenced code blocks.

Sublime can already colour any language it has a syntax for, and
``View.export_to_html`` exposes that as minihtml using the user's active colour
scheme. Highlighting fences through it means code in the preview matches code in
the editor exactly, for every installed syntax, with no bundled lexer.

Highlighting runs on hidden output panels rather than real views. Panels are
cached per syntax, since creating one per fence on every keystroke is what makes
a live preview feel slow.
"""

import re

import sublime

#: Fence info strings that Sublime does not name the way authors write them.
#: Anything not listed is resolved by scope then by syntax name, so this only
#: needs to cover genuine mismatches.
ALIASES = {
    "bash": "Bash",
    "sh": "Bash",
    "shell": "Bash",
    "zsh": "Bash",
    "console": "Bash",
    "js": "JavaScript",
    "jsx": "JavaScript",
    "node": "JavaScript",
    "ts": "TypeScript",
    "tsx": "TypeScriptReact",
    "py": "Python",
    "rb": "Ruby",
    "cr": "Crystal",
    "golang": "Go",
    "rs": "Rust",
    "yml": "YAML",
    "md": "Markdown",
    "markdown": "Markdown",
    "docker": "Dockerfile",
    "dockerfile": "Dockerfile",
    "make": "Makefile",
    "makefile": "Makefile",
    "html": "HTML",
    "xml": "XML",
    "json": "JSON",
    "jsonc": "JSON",
    "toml": "TOML",
    "ini": "INI",
    "conf": "INI",
    "sql": "SQL",
    "c++": "C++",
    "cpp": "C++",
    "cs": "C#",
    "objc": "Objective-C",
    "text": "Plain Text",
    "txt": "Plain Text",
    "": "Plain Text",
}

#: Fences whose content is a diagram or formula rather than code. The Sublime
#: target shows a placeholder for these; the browser target renders them.
NON_CODE_INFO = ("mermaid", "math", "katex", "latex")

PANEL_PREFIX = "vellum.code."

_syntax_cache = {}
_missing = object()


def normalize_info(info):
    """Reduce a fence info string to a bare lowercase language token.

    Info strings carry more than a language -- ``python title="x"`` and
    ``js{1,3}`` are both common -- so only the first word is significant.
    """
    if not info:
        return ""
    return re.split(r"[\s,{:]", info.strip(), 1)[0].strip().lower()


def find_syntax(lang):
    """Resolve a fence language to a Sublime Syntax, or None if unknown."""
    if lang in _syntax_cache:
        cached = _syntax_cache[lang]
        return None if cached is _missing else cached

    syntax = None
    name = ALIASES.get(lang)

    if name:
        matches = sublime.find_syntax_by_name(name)
        syntax = matches[0] if matches else None

    if syntax is None and lang:
        for scope in ("source." + lang, "text." + lang):
            matches = sublime.find_syntax_by_scope(scope)
            if matches:
                syntax = matches[0]
                break

    if syntax is None and lang:
        matches = sublime.find_syntax_by_name(lang)
        if not matches:
            # Sublime names are title-cased far more often than not.
            matches = sublime.find_syntax_by_name(lang.capitalize())
        syntax = matches[0] if matches else None

    _syntax_cache[lang] = syntax if syntax is not None else _missing
    return syntax


def _panel_for(window, syntax, tab_size):
    """Return a cached hidden panel already assigned `syntax`."""
    key = PANEL_PREFIX + (syntax.path if syntax else "none")
    panel = window.create_output_panel(key, unlisted=True)

    settings = panel.settings()
    if not settings.get("vellum_initialised"):
        settings.set("vellum_initialised", True)
        settings.set("gutter", False)
        settings.set("rulers", [])
        settings.set("word_wrap", False)
        settings.set("draw_white_space", "none")
        settings.set("translate_tabs_to_spaces", False)
        if syntax is not None:
            panel.assign_syntax(syntax)

    settings.set("tab_size", tab_size)
    return panel


def highlight(window, source, info, tab_size=4):
    """Return `source` as syntax-coloured minihtml.

    Falls back to escaped plain text when the language is unknown or Sublime
    declines to highlight, so an unrecognised fence still renders as code.
    """
    lang = normalize_info(info)
    syntax = find_syntax(lang)

    panel = _panel_for(window, syntax, tab_size)
    panel.run_command("select_all")
    panel.run_command("right_delete")
    panel.run_command("append", {"characters": source, "force": True, "scroll_to_end": False})

    # Trailing newlines become empty trailing lines in the export.
    end = panel.size()
    while end > 0 and panel.substr(end - 1) == "\n":
        end -= 1

    html = panel.export_to_html(
        regions=sublime.Region(0, end),
        minihtml=True,
        enclosing_tags=False,
        font_size=False,
        font_family=False,
    )
    return html, (syntax.name if syntax else None)


def split_lines(html):
    """Split exported minihtml into per-line fragments.

    ``export_to_html`` emits ``<br>`` only for newlines -- spaces come through as
    ``&nbsp;`` and everything else is wrapped in spans -- so splitting on it is
    safe and gives one fragment per source line.
    """
    return html.split("<br>")


def clear_cache(window=None):
    """Drop cached syntax lookups, and any panels belonging to `window`."""
    _syntax_cache.clear()
    if window is not None:
        for name in list(window.panels()):
            if PANEL_PREFIX in name:
                window.destroy_output_panel(name.split("output.", 1)[-1])
