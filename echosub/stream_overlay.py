# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""Captions for a live stream: a page OBS (or any streaming program) shows as a "Browser Source".

Off by default. When on, a tiny web server answers on this PC only (127.0.0.1 — nothing else on
the network can reach it) with two things: the page, and the latest captions as JSON, which the
page asks for a few times a second. The page has a transparent background, so the captions sit on
top of the stream. Nothing runs at all while it is off.
"""
import collections
import json
import logging
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger(__name__)

DEFAULT_PORT = 8790
MAX_LINES = 6

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>EchoSub captions</title>
<style>
  html, body { margin: 0; background: transparent; overflow: hidden; }
  body { font-family: "Segoe UI", Arial, sans-serif; display: flex; flex-direction: column; justify-content: flex-end;
         height: 100vh; padding: 0 24px 24px; box-sizing: border-box; }
  #captions { display: flex; flex-direction: column; align-items: center; }
  .line { margin-top: 8px; padding: 6px 14px; border-radius: 10px; background: rgba(0,0,0,.55); width: fit-content;
          max-width: 100%; text-shadow: 0 2px 3px rgba(0,0,0,.8); text-align: center; }
  .translation { font-weight: 700; }
  .original { opacity: .8; font-size: 0.6em; display: block; }
</style></head>
<body><div id="captions"></div>
<script>
  const options = new URLSearchParams(location.search);
  const size = parseInt(options.get("size") || "SIZE", 10);
  const hide = parseFloat(options.get("hide") || "HIDE");
  const showOriginal = (options.get("original") || "ORIGINAL") === "1";
  document.body.style.fontSize = size + "px";
  async function tick() {
    try {
      const reply = await fetch("captions.json", {cache: "no-store"});
      const data = await reply.json();
      const box = document.getElementById("captions");
      box.replaceChildren(...data.lines.filter(l => l.age < hide).map(l => {
        const line = document.createElement("div");
        line.className = "line";
        line.style.color = l.color;
        if (showOriginal && l.original && l.original !== l.text) {
          const o = document.createElement("span");
          o.className = "original"; o.dir = "auto"; o.textContent = l.original;
          line.appendChild(o);
        }
        const t = document.createElement("span");
        t.className = "translation"; t.dir = "auto"; t.textContent = l.text;
        line.appendChild(t);
        return line;
      }));
    } catch (e) { /* EchoSub closed or restarting: try again shortly */ }
    setTimeout(tick, 300);
  }
  tick();
</script></body></html>
"""


class _Server(ThreadingHTTPServer):
    """A port of its own: on Windows the usual "reuse" setting would let two programs share it."""
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class CaptionFeed:
    """The latest captions, written by the app and read by the server's threads."""

    def __init__(self, size=MAX_LINES):
        self._lines = collections.OrderedDict()
        self._size = size
        self._lock = threading.Lock()

    def add(self, seg_id, original, translated, color, when=None):
        with self._lock:
            self._lines[seg_id] = {"original": original or "", "text": translated or original or "",
                                   "color": color, "when": time.time() if when is None else when}
            while len(self._lines) > self._size:
                self._lines.popitem(last=False)

    def translate(self, seg_id, translated):
        with self._lock:
            if seg_id in self._lines and translated:
                self._lines[seg_id]["text"] = translated

    def clear(self):
        with self._lock:
            self._lines.clear()

    def as_json(self, count, now=None):
        now = time.time() if now is None else now
        with self._lock:
            lines = list(self._lines.values())[-max(1, int(count)):]
        return json.dumps({"lines": [{"text": line["text"], "original": line["original"], "color": line["color"],
                                      "age": round(now - line["when"], 1)} for line in lines]}, ensure_ascii=False)


def page_for(cfg):
    return (PAGE.replace("SIZE", str(int(cfg.get("stream_font_size", 42))))
            .replace("HIDE", str(max(2, int(cfg.get("stream_hide_after", 8)))))
            .replace("ORIGINAL", "1" if cfg.get("stream_show_original", True) else "0"))


class StreamServer:
    """The local web server. Only GET / and GET /captions.json; anything else is "not found"."""

    def __init__(self, feed, cfg_getter, port=DEFAULT_PORT):
        feed_, cfg_ = feed, cfg_getter

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split("?", 1)[0]
                if path == "/":
                    self._send(page_for(cfg_()).encode("utf-8"), "text/html; charset=utf-8")
                elif path == "/captions.json":
                    count = int(cfg_().get("stream_lines", 2))
                    self._send(feed_.as_json(count).encode("utf-8"), "application/json; charset=utf-8")
                else:
                    self.send_error(404)

            def _send(self, body, kind):
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):  # a request every 300 ms would flood the log
                pass

        self.httpd = _Server(("127.0.0.1", port), Handler)
        self.port = self.httpd.server_address[1]
        self._thread = threading.Thread(target=self.httpd.serve_forever, name="stream-overlay", daemon=True)
        self._thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/"

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class StreamMixin:
    """For the App: keep the stream page's captions up to date while it is switched on."""

    def apply_stream_settings(self):
        """Start or stop the server to match the settings; say so if the port is taken."""
        want = bool(self.cfg.get("stream_enabled", False))
        port = int(self.cfg.get("stream_port", DEFAULT_PORT))
        server = getattr(self, "_stream_server", None)
        if server is not None and (not want or server.port != port):
            server.stop()
            self._stream_server = server = None
        if want and server is None:
            if getattr(self, "_stream_feed", None) is None:
                self._stream_feed = CaptionFeed()
            try:
                self._stream_server = StreamServer(self._stream_feed, lambda: self.cfg, port)
                log.info("Stream captions at %s", self._stream_server.url)
            except OSError as e:
                log.warning("Could not start the stream captions on port %s: %s", port, e)
                from PySide6.QtWidgets import QSystemTrayIcon

                from . import APP_NAME

                self.tray.showMessage(APP_NAME, f"Stream captions could not use port {port} — another program "
                                      "has it. Choose another port in Settings → Stream.", QSystemTrayIcon.Warning,
                                      6000)

    def stream_final(self, seg_id, original, translated, speaker, source):
        if getattr(self, "_stream_server", None) is None:
            return
        colors = self.cfg.get("speaker_colors") or ["#FFFFFF"]
        if source == "mic":
            color = self.cfg.get("mic_color", "#8AD7FF")
        else:
            color = colors[(speaker or 0) % len(colors)] if speaker is not None else self.cfg.get("text_color")
        self._stream_feed.add(seg_id, original, translated, color or "#FFFFFF")

    def stream_translation(self, seg_id, translated):
        if getattr(self, "_stream_server", None) is not None:
            self._stream_feed.translate(seg_id, translated)

    def stop_stream(self):
        server = getattr(self, "_stream_server", None)
        if server is not None:
            server.stop()
            self._stream_server = None
