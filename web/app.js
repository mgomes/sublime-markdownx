/* Vellum browser preview client.
 *
 * Receives rendered HTML over server-sent events, then highlights code, renders
 * math and diagrams, and keeps scrolling in step with the editor.
 *
 * All libraries are served from the plugin's own vendored copies, so the page
 * works with no network access.
 */

(function () {
  "use strict";

  var TOKEN = document.body.dataset.token;
  var DOC = document.body.dataset.doc;
  var content = document.getElementById("content");
  var tocEl = document.getElementById("toc");
  var statusEl = document.getElementById("status");

  var syncEnabled = true;
  var revision = -1;
  var mermaidLoading = null;

  /* Set while applying an editor-driven scroll, so the resulting scroll event
     is not echoed back to the editor as a user action. */
  var applyingRemoteScroll = false;

  function qs(extra) {
    return "?doc=" + encodeURIComponent(DOC) + "&token=" + encodeURIComponent(TOKEN) + (extra || "");
  }

  /* -- rendering ------------------------------------------------------ */

  function render(html) {
    var anchor = topVisibleLine();
    content.innerHTML = html;

    loadMissingLanguages().then(highlight);
    renderMath();
    buildToc();
    wireCopyButtons();

    if (document.querySelector(".mermaid")) {
      loadMermaid().then(renderMermaid).catch(function () {});
    }

    /* Re-anchor to whatever was on screen so a keystroke does not scroll the
       reader away from what they were looking at. */
    if (anchor !== null && !syncEnabled) {
      scrollToLine(anchor, false);
    }
  }

  /* highlight.js ships a "common" bundle of about forty languages. Anything
     outside it -- Crystal, Elixir, Haskell and friends -- lives in its own
     module that is fetched the first time a fence asks for it, so the page
     stays small without giving up coverage. */
  var languageLoads = {};

  function loadLanguage(name) {
    if (languageLoads[name]) return languageLoads[name];
    languageLoads[name] = new Promise(function (resolve) {
      var script = document.createElement("script");
      script.src = "/vendor/languages/" + encodeURIComponent(name) + ".min.js?token=" +
        encodeURIComponent(TOKEN);
      script.onload = resolve;
      script.onerror = resolve; /* Unknown language: fall back to plain text. */
      document.head.appendChild(script);
    });
    return languageLoads[name];
  }

  function loadMissingLanguages() {
    if (!window.hljs) return Promise.resolve();

    var wanted = {};
    content.querySelectorAll("pre code[class*='language-']").forEach(function (block) {
      var match = /language-([A-Za-z0-9#+_-]+)/.exec(block.className);
      if (!match) return;
      var name = match[1].toLowerCase();
      if (!window.hljs.getLanguage(name)) wanted[name] = true;
    });

    var names = Object.keys(wanted);
    if (!names.length) return Promise.resolve();
    return Promise.all(names.map(loadLanguage));
  }

  function highlight() {
    if (!window.hljs) return;
    content.querySelectorAll("pre code").forEach(function (block) {
      try {
        window.hljs.highlightElement(block);
      } catch (err) {
        /* An unknown language is not worth breaking the page over. */
      }
    });
  }

  function renderMath() {
    if (!window.katex) return;

    content.querySelectorAll(".math-inline, .math-block").forEach(function (node) {
      var display = node.classList.contains("math-block");
      var source = node.textContent;
      try {
        window.katex.render(source, node, {
          displayMode: display,
          throwOnError: false,
          output: "html",
        });
      } catch (err) {
        node.classList.add("math-error");
        node.textContent = source;
      }
    });
  }

  function loadMermaid() {
    if (mermaidLoading) return mermaidLoading;
    mermaidLoading = new Promise(function (resolve, reject) {
      var script = document.createElement("script");
      script.src = "/vendor/mermaid.min.js?token=" + encodeURIComponent(TOKEN);
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
    return mermaidLoading;
  }

  var mermaidSeq = 0;

  function renderMermaid() {
    if (!window.mermaid) return;
    window.mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: isDark() ? "dark" : "default",
    });

    content.querySelectorAll(".mermaid").forEach(function (node) {
      var source = node.dataset.source || node.textContent;
      node.dataset.source = source;
      var id = "mermaid-" + mermaidSeq++;
      window.mermaid
        .render(id, source)
        .then(function (result) {
          node.innerHTML = result.svg;
        })
        .catch(function (err) {
          node.innerHTML = "";
          var pre = document.createElement("pre");
          pre.className = "math-error";
          pre.textContent = String(err && err.message ? err.message : err);
          node.appendChild(pre);
        });
    });
  }

  function wireCopyButtons() {
    content.querySelectorAll(".copy").forEach(function (button) {
      button.addEventListener("click", function () {
        var block = button.parentElement.querySelector("code");
        if (!block) return;
        navigator.clipboard.writeText(block.textContent).then(function () {
          button.textContent = "Copied";
          button.classList.add("done");
          setTimeout(function () {
            button.textContent = "Copy";
            button.classList.remove("done");
          }, 1200);
        });
      });
    });
  }

  /* -- contents ------------------------------------------------------- */

  function buildToc() {
    var headings = content.querySelectorAll("h1, h2, h3, h4, h5, h6");
    tocEl.innerHTML = "";
    headings.forEach(function (heading) {
      var link = document.createElement("a");
      link.href = "#" + heading.id;
      link.textContent = heading.textContent.replace(/#$/, "");
      link.className = "lvl-" + heading.tagName.substring(1);
      tocEl.appendChild(link);
    });
  }

  function updateTocHighlight() {
    var links = tocEl.querySelectorAll("a");
    if (!links.length) return;
    var best = null;
    content.querySelectorAll("h1, h2, h3, h4, h5, h6").forEach(function (heading) {
      if (heading.getBoundingClientRect().top <= 80) best = heading.id;
    });
    links.forEach(function (link) {
      link.classList.toggle("active", link.getAttribute("href") === "#" + best);
    });
  }

  /* -- scrolling ------------------------------------------------------ */

  function lineNodes() {
    return content.querySelectorAll("[data-line]");
  }

  function topVisibleLine() {
    var nodes = lineNodes();
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].getBoundingClientRect().bottom > 60) {
        return parseInt(nodes[i].dataset.line, 10);
      }
    }
    return nodes.length ? parseInt(nodes[nodes.length - 1].dataset.line, 10) : null;
  }

  function scrollToLine(line, flash) {
    var nodes = lineNodes();
    if (!nodes.length) return;

    /* Pick the last block starting at or before the requested line, so a
       cursor inside a long code block keeps that block in view. */
    var target = nodes[0];
    for (var i = 0; i < nodes.length; i++) {
      if (parseInt(nodes[i].dataset.line, 10) <= line) target = nodes[i];
      else break;
    }

    applyingRemoteScroll = true;
    var top = window.scrollY + target.getBoundingClientRect().top - 60;
    window.scrollTo({ top: Math.max(0, top), behavior: "auto" });
    setTimeout(function () {
      applyingRemoteScroll = false;
    }, 60);

    if (flash) {
      target.classList.remove("flash");
      void target.offsetWidth;
      target.classList.add("flash");
    }
  }

  var scrollTimer = null;

  window.addEventListener(
    "scroll",
    function () {
      updateTocHighlight();
      if (!syncEnabled || applyingRemoteScroll) return;

      clearTimeout(scrollTimer);
      scrollTimer = setTimeout(function () {
        var line = topVisibleLine();
        if (line === null) return;
        fetch("/scroll" + qs(), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ line: line }),
          keepalive: true,
        }).catch(function () {});
      }, 120);
    },
    { passive: true }
  );

  /* -- theme ---------------------------------------------------------- */

  function isDark() {
    var explicit = document.documentElement.dataset.theme;
    if (explicit) return explicit === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  document.getElementById("toggle-theme").addEventListener("click", function () {
    document.documentElement.dataset.theme = isDark() ? "light" : "dark";
    if (document.querySelector(".mermaid")) renderMermaid();
  });

  document.getElementById("toggle-toc").addEventListener("click", function (event) {
    tocEl.hidden = !tocEl.hidden;
    event.currentTarget.classList.toggle("on", !tocEl.hidden);
  });

  document.getElementById("toggle-sync").addEventListener("click", function (event) {
    syncEnabled = !syncEnabled;
    event.currentTarget.classList.toggle("on", syncEnabled);
  });

  /* -- transport ------------------------------------------------------ */

  function connect() {
    var source = new EventSource("/events" + qs());

    source.onopen = function () {
      statusEl.classList.add("live");
      statusEl.title = "Connected to Sublime Text";
    };

    source.onmessage = function (event) {
      var payload = JSON.parse(event.data);
      if (payload.type === "content") {
        if (payload.revision === revision) return;
        revision = payload.revision;
        render(payload.html);
      } else if (payload.type === "scroll" && syncEnabled) {
        scrollToLine(payload.line, true);
      }
    };

    source.onerror = function () {
      statusEl.classList.remove("live");
      statusEl.title = "Disconnected -- the preview may have been closed in Sublime Text";
      /* EventSource retries on its own; nothing to do but reflect the state. */
    };
  }

  connect();
})();
