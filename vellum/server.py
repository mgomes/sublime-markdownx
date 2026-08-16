"""Local HTTP server backing the browser preview.

Started only when a browser preview is opened and stopped when the last one
closes, so the Sublime-only path never opens a port.

Live updates go out over server-sent events rather than WebSockets. Updates only
ever flow server to browser, which is exactly what SSE provides, and it needs
nothing beyond ``http.server`` -- a WebSocket would mean hand-rolling the
handshake and frame codec against no dependency at all.

Access is restricted three ways: the listener binds to loopback, every request
must carry a token minted at startup, and file reads are confined to the
directories of documents actually being previewed.
"""

import json
import mimetypes
import os
import posixpath
import queue
import secrets
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WEB_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")

#: Sent periodically so proxies and browsers keep the event stream open.
HEARTBEAT_SECONDS = 25


class Session:
    """One previewed document and the browser tabs watching it."""

    def __init__(self, key, title, directory):
        self.key = key
        self.title = title
        self.directory = directory
        self.html = ""
        self.revision = 0
        self.scroll_line = None
        self.clients = []
        self.lock = threading.Lock()
        #: Set by the server when a browser reports its scroll position.
        self.on_scroll = None

    def update(self, html, title=None):
        with self.lock:
            self.revision += 1
            self.html = html
            if title:
                self.title = title
            payload = {"type": "content", "revision": self.revision, "html": html}
            clients = list(self.clients)
        _broadcast(clients, payload)

    def scroll_to(self, line):
        with self.lock:
            clients = list(self.clients)
        _broadcast(clients, {"type": "scroll", "line": line})

    def add_client(self):
        channel = queue.Queue(maxsize=32)
        with self.lock:
            self.clients.append(channel)
            initial = {"type": "content", "revision": self.revision, "html": self.html}
        channel.put(initial)
        return channel

    def remove_client(self, channel):
        with self.lock:
            if channel in self.clients:
                self.clients.remove(channel)

    def client_count(self):
        with self.lock:
            return len(self.clients)


def _broadcast(clients, payload):
    for channel in clients:
        try:
            channel.put_nowait(payload)
        except queue.Full:
            # A tab that has stopped reading is left behind rather than
            # blocking the editor; it recovers on its next reconnect.
            pass


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # Silence per-request logging to Sublime's console.
    def log_message(self, fmt, *args):
        pass

    # -- helpers ---------------------------------------------------------

    def _query(self):
        parsed = urllib.parse.urlparse(self.path)
        return parsed.path, urllib.parse.parse_qs(parsed.query)

    def _authorised(self, params):
        token = (params.get("token") or [""])[0]
        return secrets.compare_digest(token, self.server.token)

    def _send(self, code, body=b"", content_type="text/plain; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    # -- routes ----------------------------------------------------------

    def do_GET(self):
        path, params = self._query()

        if not self._authorised(params):
            self._send(403, b"forbidden")
            return

        if path == "/":
            self._serve_shell(params)
        elif path == "/events":
            self._serve_events(params)
        elif path.startswith("/vendor/") or path.startswith("/static/"):
            self._serve_web_asset(path)
        elif path.startswith("/file/"):
            self._serve_document_file(path, params)
        else:
            self._send(404, b"not found")

    def do_POST(self):
        path, params = self._query()
        if not self._authorised(params):
            self._send(403, b"forbidden")
            return

        if path != "/scroll":
            self._send(404, b"not found")
            return

        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send(400, b"bad request")
            return

        session = self.server.sessions.get((params.get("doc") or [""])[0])
        if session and session.on_scroll:
            try:
                session.on_scroll(int(payload.get("line", 0)))
            except (TypeError, ValueError):
                pass
        self._send(204)

    # -- handlers --------------------------------------------------------

    def _serve_shell(self, params):
        key = (params.get("doc") or [""])[0]
        session = self.server.sessions.get(key)
        if session is None:
            self._send(404, b"no such preview")
            return

        try:
            with open(os.path.join(WEB_ROOT, "index.html"), encoding="utf-8") as handle:
                shell = handle.read()
        except OSError as error:
            self._send(500, str(error).encode("utf-8"))
            return

        shell = (
            shell.replace("{{TOKEN}}", self.server.token)
            .replace("{{DOC}}", urllib.parse.quote(key))
            .replace("{{TITLE}}", session.title)
        )
        self._send(200, shell.encode("utf-8"), "text/html; charset=utf-8")

    def _serve_events(self, params):
        key = (params.get("doc") or [""])[0]
        session = self.server.sessions.get(key)
        if session is None:
            self._send(404, b"no such preview")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        channel = session.add_client()
        try:
            while not self.server.stopping:
                try:
                    payload = channel.get(timeout=HEARTBEAT_SECONDS)
                    frame = "data: %s\n\n" % json.dumps(payload)
                except queue.Empty:
                    frame = ": keep-alive\n\n"
                self.wfile.write(frame.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # Tab closed.
        finally:
            session.remove_client(channel)

    def _serve_web_asset(self, path):
        # /static/ is the page's own assets at the root of web/; /vendor/ keeps
        # its prefix because those files live in web/vendor/.
        if path.startswith("/static/"):
            relative = path[len("/static/") :]
        else:
            relative = path.lstrip("/")

        relative = posixpath.normpath(urllib.parse.unquote(relative)).lstrip("/")
        target = os.path.normpath(os.path.join(WEB_ROOT, relative))
        if not _within(target, WEB_ROOT):
            self._send(403, b"forbidden")
            return
        self._send_file(target)

    def _serve_document_file(self, path, params):
        """Serve an image or link target relative to a previewed document."""
        session = self.server.sessions.get((params.get("doc") or [""])[0])
        if session is None or not session.directory:
            self._send(404, b"not found")
            return

        relative = urllib.parse.unquote(path[len("/file/") :])
        target = os.path.normpath(os.path.join(session.directory, relative))
        if not _within(target, session.directory):
            self._send(403, b"forbidden")
            return
        self._send_file(target)

    def _send_file(self, target):
        try:
            with open(target, "rb") as handle:
                body = handle.read()
        except OSError:
            self._send(404, b"not found")
            return

        guessed = mimetypes.guess_type(target)[0] or "application/octet-stream"
        self._send(200, body, guessed)


def _within(target, root):
    """True when `target` is inside `root`, resolving symlinks and ``..``."""
    try:
        root = os.path.realpath(root)
        target = os.path.realpath(target)
    except OSError:
        return False
    return target == root or target.startswith(root + os.sep)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler):
        super().__init__(address, handler)
        self.token = secrets.token_urlsafe(24)
        self.sessions = {}
        self.stopping = False


_server = None
_lock = threading.Lock()


def ensure_running():
    """Start the server if it is not already up, and return it."""
    global _server
    with _lock:
        if _server is None:
            # Port 0 asks the OS for a free port, so nothing can collide.
            _server = _Server(("127.0.0.1", 0), _Handler)
            thread = threading.Thread(
                target=_server.serve_forever, name="vellum-http", daemon=True
            )
            thread.start()
        return _server


def stop_if_idle():
    """Shut the server down once no session remains."""
    global _server
    with _lock:
        if _server is not None and not _server.sessions:
            _server.stopping = True
            _server.shutdown()
            _server.server_close()
            _server = None
            return True
    return False


def open_session(key, title, directory):
    server = ensure_running()
    session = server.sessions.get(key)
    if session is None:
        session = Session(key, title, directory)
        server.sessions[key] = session
    else:
        session.title = title
        session.directory = directory
    return session


def close_session(key):
    server = _server
    if server is not None:
        server.sessions.pop(key, None)
    stop_if_idle()


def url_for(key):
    """Return the browser URL for a session, or None if nothing is running."""
    server = _server
    if server is None:
        return None
    port = server.server_address[1]
    return "http://127.0.0.1:%d/?doc=%s&token=%s" % (
        port,
        urllib.parse.quote(key),
        server.token,
    )


def base_url_for(key):
    """Return the prefix that resolves document-relative asset URLs."""
    server = _server
    if server is None:
        return ""
    port = server.server_address[1]
    return "http://127.0.0.1:%d/file/" % port


def asset_query(key):
    """Query string appended to document-relative asset URLs."""
    server = _server
    if server is None:
        return ""
    return "?doc=%s&token=%s" % (urllib.parse.quote(key), server.token)
