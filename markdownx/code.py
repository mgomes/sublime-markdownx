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

#: Labels for which Plain Text is the right answer rather than a failed lookup.
PLAIN_TEXT_INFO = ("text", "txt", "plain", "plaintext", "")

PANEL_PREFIX = "markdownx.code."

_syntax_cache = {}
_missing = object()


def normalize_info(info):
    """Reduce a fence info string to a bare lowercase language token.

    Info strings carry more than a language -- ``python title="x"`` and
    ``js{1,3}`` are both common -- so only the first word is significant.
    """
    if not info:
        return ""
    return re.split(r"[\s,{:]", info.strip(), maxsplit=1)[0].strip().lower()


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

    if syntax is None and lang:
        # Fences are commonly labelled with a file extension rather than the
        # syntax name -- ```vibe, ```cr, ```rs. Sublime already maps extensions
        # to syntaxes, so asking it beats keeping a table in step by hand, and
        # it picks up any syntax the user installs later.
        guess = sublime.find_syntax_for_file("untitled." + lang)
        # Unknown extensions come back as Plain Text rather than None, which
        # would otherwise mask a genuinely unrecognised language.
        if guess is not None and (guess.scope != "text.plain" or lang in PLAIN_TEXT_INFO):
            syntax = guess

    _syntax_cache[lang] = syntax if syntax is not None else _missing
    return syntax


def _panel_for(window, syntax, tab_size):
    """Return a cached hidden panel already assigned `syntax`."""
    key = PANEL_PREFIX + (syntax.path if syntax else "none")
    panel = window.create_output_panel(key, unlisted=True)

    settings = panel.settings()
    if not settings.get("markdownx_initialised"):
        settings.set("markdownx_initialised", True)
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


def _tokenize(html):
    """Walk exported minihtml as ``(kind, text)`` pairs.

    Yields ``("tag", ...)`` for markup and ``("char", ...)`` for one unit of
    visible width, so a caller can count columns without counting markup. HTML
    entities such as ``&nbsp;`` and ``&amp;`` are single visible characters
    despite being several bytes.
    """
    index = 0
    length = len(html)
    while index < length:
        char = html[index]
        if char == "<":
            end = html.find(">", index)
            if end == -1:
                yield "char", html[index:]
                return
            yield "tag", html[index : end + 1]
            index = end + 1
        elif char == "&":
            end = html.find(";", index)
            if end == -1 or end - index > 10:
                yield "char", char
                index += 1
            else:
                yield "char", html[index : end + 1]
                index = end + 1
        else:
            yield "char", char
            index += 1


def wrap_line(html, width, indent=2):
    """Soft-wrap one highlighted line to `width` visible characters.

    minihtml offers no horizontal scrolling and no width property, so a single
    long code line would otherwise stretch the whole preview and stop every
    paragraph in the document from wrapping at the pane edge.

    Colour is preserved across the break by closing the open span before the
    newline and reopening it after, which is safe because ``export_to_html``
    emits a flat run of spans with no nesting.
    """
    if width < 10:
        return html

    open_tag = None
    column = 0
    out = []
    continuation = "&nbsp;" * indent

    for kind, text in _tokenize(html):
        if kind == "tag":
            if text.startswith("</"):
                open_tag = None
            elif not text.startswith("<br"):
                open_tag = text
            out.append(text)
            continue

        if column >= width:
            if open_tag:
                out.append("</span>")
            out.append("<br>" + continuation)
            if open_tag:
                out.append(open_tag)
            column = indent

        out.append(text)
        column += 1

    return "".join(out)


def clear_cache(window=None):
    """Drop cached syntax lookups, and any panels belonging to `window`."""
    _syntax_cache.clear()
    if window is not None:
        for name in list(window.panels()):
            if PANEL_PREFIX in name:
                window.destroy_output_panel(name.split("output.", 1)[-1])
