# MarkdownX

A live markdown preview for Sublime Text 4, with GitHub tables, syntax-highlighted
code fences, and two render targets.

`cmd+shift+m` opens a preview pane beside the buffer that updates as you type.
`cmd+shift+alt+m` opens the same document in a browser, where diagrams and math
render too.

## The two targets

Sublime's in-editor HTML dialect, minihtml, implements no table layout, no
`<pre>`, and no JavaScript engine. So the pane and the browser get separate
renderers over one shared parse, each playing to what its surface can do.

| | Preview in Sublime | Preview in Browser |
|:--|:--|:--|
| Surface | pane beside the buffer | browser tab |
| Code fences | Sublime's own syntax engine, in your colour scheme | highlight.js, GitHub theme |
| Tables | aligned monospace columns, header rule, zebra striping | real `<table>` |
| Mermaid | placeholder linking to the browser | rendered |
| Math | placeholder linking to the browser | rendered with KaTeX |
| Live update | as you type | as you type |
| Scroll sync | editor to pane | both ways |
| Network | none, no port opened | loopback only, started on demand |

The pane is the default and never opens a port. The HTTP server starts only when
you open a browser preview and stops when the last one closes.

Fenced code in the pane goes through `View.export_to_html`, so it is coloured by
whatever colour scheme you already use, across every syntax Sublime has installed
— including ones highlight.js does not ship, like Crystal.

## Commands

| Command | Binding |
|:--|:--|
| MarkdownX: Preview in Sublime | `cmd+shift+m` |
| MarkdownX: Preview in Browser | `cmd+shift+alt+m` |
| MarkdownX: Export to HTML | — |
| MarkdownX: Refresh Preview | — |

Export writes a single self-contained `.html` file with all CSS and JavaScript
inlined. Mermaid and KaTeX are embedded only when the document uses them, so an
ordinary document exports at around 140 KB rather than 4 MB.

## Markdown support

CommonMark plus the GitHub extensions: tables with alignment, task lists,
strikethrough, autolinks, footnotes, definition lists, highlight, superscript and
subscript, and YAML front matter. Math is written as `$inline$` and `$$block$$`,
including the single-line `$$…$$` form GitHub accepts.

## Settings

`Preferences → Package Settings → MarkdownX → Settings`. Every option is
documented in the default file; the ones most people want are the two fonts:

```json
{
    "code_font": "MonoLisaCode",
    "body_font": "Helvetica Neue",
    "font_size": 15,
    "code_font_size": 12
}
```

`code_font` is the monospace face, used for fenced code, inline code, tables and
list markers — everything whose alignment depends on a fixed character width.
`body_font` is the proportional face for prose. Both default to following the
editor: code uses your `font_face`, body uses the UI font.

## Installing

The package has no dependencies. Clone it into your Packages directory, or clone
it anywhere and symlink:

```bash
git clone https://github.com/YOURNAME/sublime-markdownx.git
ln -s "$PWD/sublime-markdownx" \
  "$HOME/Library/Application Support/Sublime Text/Packages/MarkdownX"
```

Requires Sublime Text build 4092 or newer, which is where `export_to_html`
arrived. Markdown parsing uses a vendored copy of
[mistune](https://github.com/lepture/mistune) (BSD-3-Clause).

## Development

```bash
python3 -m unittest discover -s tests -t .   # parsing, tables, wrapping
dev/reload.sh                                # reload inside a running Sublime
dev/probe.sh 'report(x=sublime.version())'   # run a snippet in the plugin host
```

Sublime exposes no CLI for running plugin commands, which makes behaviour hard to
check without clicking through the UI. `dev/probe.sh` sends a Python snippet to
the running editor and prints what it reports, so the plugin can be exercised
from a script. It is inert unless `~/.markdownx-probe` exists.

`tests/fixtures/kitchen-sink.md` exercises every supported construct in one
document and is the fastest way to spot a regression in either target.
