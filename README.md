# MarkdownX

MarkdownX shows a live preview of your Markdown in Sublime Text 4. You can show
the preview next to the file or open it in a browser. The browser view adds full
tables, Mermaid diagrams, math, and a table of contents.

Both views update as you type. All preview libraries are included with the
package. Your document is not sent to a remote service.

![Sublime Text showing a Markdown file on the left and the MarkdownX preview
pane on the right, with a table and highlighted Go code](./docs/images/sublime-pane-dark.png)

*The Sublime pane: source on the left, preview on the right.*

## Install from GitHub

MarkdownX requires Sublime Text build 4092 or newer.

1. In Sublime Text, choose `Preferences → Browse Packages…`.
2. Open a terminal in the directory that appears.
3. Clone this repository into a directory named `MarkdownX`:

   ```bash
   git clone https://github.com/mgomes/sublime-markdownx.git MarkdownX
   ```

Sublime Text loads the package after the clone finishes. The package includes
all of its runtime libraries. Markdown parsing uses [Mistune](https://github.com/lepture/mistune)
(BSD-3-Clause). highlight.js, Mermaid, and KaTeX are included as well.

## Preview a document

Open a Markdown file and use one of these commands:

| Command | macOS | Linux and Windows |
|:--|:--|:--|
| MarkdownX: Preview in Sublime | `Cmd+Shift+M` | `Ctrl+Shift+M` |
| MarkdownX: Preview in Browser | `Cmd+Shift+Option+M` | `Ctrl+Shift+Alt+M` |

The first command opens or closes the preview pane. The second opens the
document in your browser. You can also find both commands in the Command Palette
and the Markdown context menu.

Two more commands are available in the Command Palette:

- **MarkdownX: Export to HTML** saves the document as an `.html` file.
- **MarkdownX: Refresh Preview** reloads the Sublime preview.

## Preview options

| Feature | Sublime pane | Browser |
|:--|:--|:--|
| Code fences | Sublime syntax highlighting and the current color scheme | bundled highlight.js |
| Tables | aligned text; long cells are shortened | full HTML tables |
| Mermaid and math | source with a link to the browser | rendered |
| Scrolling | editor to pane | both directions |
| Server | none | local only, started when needed |

Use the Sublime pane for quick feedback while you write. Use the browser when
you need diagrams, math, wide tables, or the table of contents.

![The browser preview showing the table of contents, a task list, a table, and
a highlighted Go code block](./docs/images/browser-light.png)

*The browser preview, with the table of contents open.*

![The same document in the browser dark theme, with a Mermaid flowchart and two
KaTeX equations rendered](./docs/images/browser-dark.png)

*Further down the same document: Mermaid and math, in the dark theme.*

Code fences in the pane use the same syntax highlighting as your editor. The
browser uses its own bundled highlighting.

The browser preview runs only on your computer. It stops when you close the last
previewed document.

## Supported Markdown

MarkdownX supports standard Markdown plus:

- GitHub-style tables with alignment, task lists, strikethrough, plain URLs that
  become links, and footnotes.
- Definition lists and abbreviations.
- `==highlight==`, `^^insertion^^`, `H~2~O`, and `x^2^` inline formatting.
- YAML front matter.
- Mermaid diagrams in fenced `mermaid` blocks.
- KaTeX math written as `$inline$` or `$$block$$`, including GitHub's
  single-line `$$…$$` form.

In the Sublime pane, Mermaid and math show their source with a link to the
browser. The browser renders them.

## Export to HTML

**MarkdownX: Export to HTML** saves one file with the styles and scripts needed
to display the preview. Math adds KaTeX and its fonts. Mermaid adds Mermaid.

A plain document is about 140 KB. A document with math is about 785 KB. A
document with Mermaid is about 3.7 MB.

Images and linked files are not copied into the HTML file. Keep local files next
to the exported file, or use URLs that will remain available.

## Customize the Sublime pane

Open `Preferences → Package Settings → MarkdownX → Settings`. The [default
settings](./MarkdownX.sublime-settings) file describes every option.

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

`auto_open` opens the pane when a Markdown file loads. `scroll_sync` keeps the
editor and preview aligned. The font settings control the pane. By default, code
uses the editor font and prose uses the system font. The browser has its own
light and dark theme button.

![The same file previewed in Sublime Text with a light color
scheme](./docs/images/sublime-pane-light.png)

*The pane takes its colors from your editor color scheme.*

## Develop and verify

```bash
python3 -m unittest discover -s tests -t .
dev/reload.sh
dev/probe.sh 'report(build=sublime.version())'
```

The tests run without a network connection. They check Markdown parsing, table
layout, and code wrapping. Sublime has no command-line tool for plugin commands,
so `dev/probe.sh` sends a small Python command to a running editor and prints the
result. The script creates `~/.markdownx-probe`; remove that directory to turn it
off.

[`tests/fixtures/kitchen-sink.md`](./tests/fixtures/kitchen-sink.md) contains
every supported construct. It is the quickest visual test for both previews.
[`docs/demo.md`](./docs/demo.md) is the shorter document in the screenshots
above.
