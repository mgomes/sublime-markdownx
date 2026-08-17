# MarkdownX

MarkdownX adds live Markdown preview to Sublime Text 4. Use a native split pane
for everyday editing, or open a browser view for full tables, Mermaid diagrams,
KaTeX math, and a document outline.

Both previews update as you type and follow the editor's scroll position. Their
rendering libraries are bundled, so MarkdownX does not send your document to a
remote service.

## Install from GitHub

MarkdownX requires Sublime Text build 4092 or newer.

1. In Sublime Text, choose `Preferences → Browse Packages…`.
2. Open a terminal in the directory that appears.
3. Clone this repository into a directory named `MarkdownX`:

   ```bash
   git clone https://github.com/mgomes/sublime-markdownx.git MarkdownX
   ```

Sublime Text loads the package as soon as the clone finishes. MarkdownX has no
external runtime dependencies. Markdown parsing uses a vendored copy of
[Mistune](https://github.com/lepture/mistune) (BSD-3-Clause); highlight.js,
Mermaid, KaTeX, and their required assets are bundled too.

## Preview a document

Open a Markdown file and use either preview command:

| Command | macOS | Linux and Windows |
|:--|:--|:--|
| MarkdownX: Preview in Sublime | `Cmd+Shift+M` | `Ctrl+Shift+M` |
| MarkdownX: Preview in Browser | `Cmd+Shift+Option+M` | `Ctrl+Shift+Alt+M` |

The first command toggles a preview pane beside the current buffer. The second
opens the document in your browser. Both commands are also available from the
Command Palette and the Markdown context menu.

Two more commands are available from the Command Palette:

- **MarkdownX: Export to HTML** writes the rendered document to an `.html` file.
- **MarkdownX: Refresh Preview** clears cached syntax lookups and redraws the
  Sublime pane.

## Preview options

| Capability | Sublime pane | Browser |
|:--|:--|:--|
| Code fences | installed Sublime syntaxes and the current colour scheme | bundled highlight.js with light and dark themes |
| Tables | aligned monospace columns, capped to the pane width | native HTML tables with horizontal overflow |
| Mermaid and math | source placeholder with a link to the browser | rendered with Mermaid and KaTeX |
| Navigation | editor-to-pane scroll sync | two-way scroll sync and a contents sidebar |
| Local server | none | token-protected loopback server, started on demand |

Sublime's in-editor HTML dialect, minihtml, has no table layout, `<pre>` block,
or JavaScript engine. MarkdownX parses the document once, then renders it for
each target so the pane can stay lightweight while the browser handles the
features that need full HTML and JavaScript.

Fenced code in the pane passes through `View.export_to_html`, so highlighting
matches the active colour scheme and uses every syntax package installed in
Sublime. The browser uses the bundled highlight.js grammars instead.

The pane never opens a port. A browser preview starts a token-protected server
bound to `127.0.0.1`; the server stops after the last previewed document closes.

## Supported Markdown

MarkdownX parses CommonMark and adds:

- GitHub-style tables with alignment, task lists, strikethrough, URL autolinks,
  and footnotes.
- Definition lists and abbreviations.
- `==highlight==`, `^^insertion^^`, `H~2~O`, and `x^2^` inline formatting.
- YAML front matter.
- Mermaid diagrams in fenced `mermaid` blocks.
- KaTeX math written as `$inline$` or `$$block$$`, including GitHub's
  single-line `$$…$$` form.

The Sublime pane keeps Mermaid and math source visible as a placeholder; follow
its link to render the construct in the browser.

## Export a portable HTML file

**MarkdownX: Export to HTML** writes one file with MarkdownX's styles and scripts
inlined. When math is present, it also inlines KaTeX's fonts. A plain document is
about 140 KB, one with math is about 785 KB, and one with Mermaid is about 3.7
MB; feature-specific assets are included only when the document needs them.

Document images and linked files are not embedded. Keep relative assets beside
the exported file when moving it, or use URLs that remain reachable.

## Customize the Sublime pane

Open `Preferences → Package Settings → MarkdownX → Settings`. Every option is
documented in the [default settings](./MarkdownX.sublime-settings); a typical
override looks like this:

```json
{
    "auto_open": true,
    "scroll_sync": true,
    "table_max_width": 100,
    "code_line_numbers": true,
    "code_font": "MonoLisaCode",
    "body_font": "Helvetica Neue",
    "font_size": 15,
    "code_font_size": 12
}
```

`auto_open` opens the Sublime pane whenever a Markdown file loads. Font and line
number settings affect that pane; by default, code follows the editor font and
prose uses the system UI font. The browser has its own light and dark theme
toggle.

## Develop and verify

```bash
python3 -m unittest discover -s tests -t .
dev/reload.sh
dev/probe.sh 'report(build=sublime.version())'
```

The offline test suite covers parsing, table layout, and code wrapping. Sublime
Text exposes no command-line interface for plugin commands, so `dev/probe.sh`
sends a Python snippet to a running editor and prints the reported values. The
script creates `~/.markdownx-probe`; remove that directory to disable the bridge.

[`tests/fixtures/kitchen-sink.md`](./tests/fixtures/kitchen-sink.md) exercises
every supported construct in one document and is the fastest visual regression
check for both render targets.
