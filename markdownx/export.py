"""Builds browser-target HTML, both live and as a standalone file.

The live page receives only the rendered body, since the shell and its assets
are already loaded and served. An export instead inlines everything into one
file that opens anywhere with no server and no network.

Mermaid and KaTeX are inlined only when the document actually uses them.
Unconditionally embedding Mermaid would add 3.5 MB to every export; most
documents contain no diagrams and stay around 150 KB.
"""

import base64
import os
import re

from .parse import create_parser, split_front_matter
from .render_web import WebRenderer
from .util import escape

WEB_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
VENDOR = os.path.join(WEB_ROOT, "vendor")

#: Rewritten to data URIs when KaTeX's stylesheet is inlined.
FONT_URL_RE = re.compile(r"url\(fonts/([A-Za-z0-9_-]+\.woff2)\)")

#: Fence names that highlight.js treats as aliases. An alias resolves only once
#: its grammar is registered, so it has to be mapped to the module defining it.
#: Kept in step with LANGUAGE_ALIASES in web/app.js.
LANGUAGE_ALIASES = {
    "console": "shell",
    "shell-session": "shell",
    "shellsession": "shell",
    "html": "xml",
    "xhtml": "xml",
    "svg": "xml",
    "yml": "yaml",
    "docker": "dockerfile",
    "make": "makefile",
    "mk": "makefile",
    "objc": "objectivec",
    "obj-c": "objectivec",
    "ps": "powershell",
    "ps1": "powershell",
    "ex": "elixir",
    "exs": "elixir",
    "cr": "crystal",
    "hs": "haskell",
    "clj": "clojure",
    "tex": "latex",
    "fs": "fsharp",
}


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as handle:
        return handle.read()


def render_body(text, base_url="", asset_query="", settings=None):
    """Render markdown to a body fragment plus the feature flags it needs."""
    front_matter, body, offset = split_front_matter(text)

    renderer = WebRenderer(base_url=base_url, asset_query=asset_query, settings=settings)
    md = create_parser(renderer)
    html, _state = md.parse(body)

    if offset:
        html = _shift_lines(html, offset)

    if front_matter and (settings or {}).get("show_front_matter", True):
        html = '<pre class="front-matter">%s</pre>\n%s' % (escape(front_matter), html)

    return {
        "html": html,
        "uses_mermaid": renderer.uses_mermaid,
        "uses_math": renderer.uses_math,
        "headings": renderer.headings,
        "languages": sorted(set(re.findall(r'class="language-([A-Za-z0-9#+_-]+)"', html))),
    }


def _shift_lines(html, offset):
    """Advance every data-line past the front matter that was stripped."""
    return re.sub(
        r'data-line="(\d+)"',
        lambda m: 'data-line="%d"' % (int(m.group(1)) + offset),
        html,
    )


def _modules_for(languages):
    """Vendored grammar modules needed for `languages`, deduplicated.

    Names already covered by the common bundle have no module on disk and are
    skipped; so is anything genuinely unknown, which then renders unhighlighted.
    """
    wanted = []
    for name in languages:
        module = LANGUAGE_ALIASES.get(name, name)
        if module in wanted:
            continue
        if os.path.exists(os.path.join(VENDOR, "languages", "%s.min.js" % module)):
            wanted.append(module)
    return wanted


def _inline_katex_css():
    """KaTeX's stylesheet with its woff2 faces embedded as data URIs."""
    css = _read(VENDOR, "katex.min.css")

    def embed(match):
        path = os.path.join(VENDOR, "fonts", match.group(1))
        try:
            with open(path, "rb") as handle:
                blob = base64.b64encode(handle.read()).decode("ascii")
        except OSError:
            return match.group(0)
        return "url(data:font/woff2;base64,%s)" % blob

    return FONT_URL_RE.sub(embed, css)


def standalone(title, text, settings=None):
    """Render `text` into a single self-contained HTML document."""
    result = render_body(text, settings=settings)

    parts = [_read(WEB_ROOT, "styles.css"), _read(VENDOR, "hljs-light.css")]

    dark = _read(VENDOR, "hljs-dark.css")
    parts.append("@media (prefers-color-scheme: dark) {\n%s\n}" % dark)
    parts.append(':root[data-theme="dark"] {}\n')

    scripts = [_read(VENDOR, "highlight.min.js")]

    # highlight.js's common bundle covers about forty languages; anything else
    # has its own module, and only the ones this document uses are inlined.
    for name in _modules_for(result["languages"]):
        scripts.append(_read(VENDOR, "languages", "%s.min.js" % name))

    if result["uses_math"]:
        parts.append(_inline_katex_css())
        scripts.append(_read(VENDOR, "katex.min.js"))
    if result["uses_mermaid"]:
        scripts.append(_read(VENDOR, "mermaid.min.js"))

    boot = EXPORT_BOOT % {
        "math": "true" if result["uses_math"] else "false",
        "mermaid": "true" if result["uses_mermaid"] else "false",
    }
    scripts.append(boot)

    return EXPORT_SHELL % {
        "title": escape(title),
        "css": "\n".join(parts),
        "js": "\n;\n".join(scripts),
        "body": result["html"],
    }


EXPORT_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<style>
%(css)s
/* The export has no toolbar, so the prose owns the page. */
.markdown-body { padding-top: 40px; padding-bottom: 40px; }
</style>
</head>
<body>
<div class="layout">
<main class="markdown-body" id="content">
%(body)s
</main>
</div>
<script>
%(js)s
</script>
</body>
</html>
"""

EXPORT_BOOT = """
(function () {
  "use strict";
  var content = document.getElementById("content");

  if (window.hljs) {
    content.querySelectorAll("pre code").forEach(function (block) {
      try { window.hljs.highlightElement(block); } catch (e) {}
    });
  }

  if (%(math)s && window.katex) {
    content.querySelectorAll(".math-inline, .math-block").forEach(function (node) {
      var display = node.classList.contains("math-block");
      var src = node.textContent;
      try {
        window.katex.render(src, node, { displayMode: display, throwOnError: false });
      } catch (e) {
        node.classList.add("math-error");
        node.textContent = src;
      }
    });
  }

  if (%(mermaid)s && window.mermaid) {
    var dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    window.mermaid.initialize({ startOnLoad: false, theme: dark ? "dark" : "default" });
    content.querySelectorAll(".mermaid").forEach(function (node, index) {
      window.mermaid.render("m" + index, node.textContent)
        .then(function (r) { node.innerHTML = r.svg; })
        .catch(function () {});
    });
  }

  content.querySelectorAll(".copy").forEach(function (button) {
    button.addEventListener("click", function () {
      var code = button.parentElement.querySelector("code");
      if (!code) return;
      navigator.clipboard.writeText(code.textContent).then(function () {
        button.textContent = "Copied";
        setTimeout(function () { button.textContent = "Copy"; }, 1200);
      });
    });
  });
})();
"""
