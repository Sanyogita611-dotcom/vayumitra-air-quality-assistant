"""VayuMitra AI — Urban Air Quality Voice, Vision & Daily Routine Assistant HTTP Server."""

import json
import logging
import os
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from services.environment_service import get_live_environment
from services.gemini_service import HAS_GENAI, handle_chat_logic, handle_routine_logic
from services.geocode_service import forward_geocode_query, reverse_geocode_coordinates

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vayumitra.server")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MAX_REQUEST_BODY_BYTES = 15 * 1024 * 1024  # 15 MB safety limit

FAVICON_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    b'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
    b'<stop offset="0%" stop-color="#14b8a6"/><stop offset="100%" stop-color="#38bdf8"/>'
    b'</linearGradient></defs>'
    b'<rect width="64" height="64" rx="16" fill="url(#g)"/>'
    b'<path d="M14 26h24a6 6 0 1 0-6-6M14 36h32a6 6 0 1 1-6 6M14 46h16" '
    b'fill="none" stroke="#fff" stroke-width="4.5" stroke-linecap="round"/>'
    b'</svg>'
)


class VayuMitraHTTPRequestHandler(SimpleHTTPRequestHandler):
    """Hardened static + JSON API handler with security headers and safe static serving."""

    # Explicit MIME map prevents Windows Registry from serving .js as text/plain (blocked by nosniff)
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "application/javascript; charset=utf-8",
        ".mjs": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        super().end_headers()

    def _send_json(self, status_code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_static_safe(self, rel_path: str):
        """Serve files strictly from STATIC_DIR; reject path traversal, dotfiles, and missing files."""
        clean_rel = urllib.parse.unquote(rel_path).lstrip("/")
        if not clean_rel or clean_rel.startswith(".") or "/." in clean_rel or "\\" in clean_rel or ".." in clean_rel:
            self._send_json(404, {"detail": "Not found"})
            return
        static_root = os.path.realpath(STATIC_DIR)
        target_path = os.path.realpath(os.path.join(static_root, clean_rel))
        if not target_path.startswith(static_root + os.sep) or not os.path.isfile(target_path):
            self._send_json(404, {"detail": "Not found"})
            return
        super().do_GET()

    def _read_json_body(self) -> tuple[Optional[dict], Optional[tuple[int, dict]]]:
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return None, (400, {"detail": "Invalid Content-Length header"})
        if content_length < 0:
            return None, (400, {"detail": "Invalid Content-Length header"})
        if content_length > MAX_REQUEST_BODY_BYTES:
            return None, (413, {"detail": "Request payload too large (max 15 MB)."})
        raw_body = self.rfile.read(content_length).decode("utf-8", errors="replace") if content_length > 0 else "{}"
        try:
            payload = json.loads(raw_body)
            if not isinstance(payload, dict):
                return None, (400, {"detail": "JSON request body must be an object."})
            return payload, None
        except Exception:
            return None, (400, {"detail": "Invalid JSON request body."})

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            index_path = os.path.join(STATIC_DIR, "index.html")
            with open(index_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        elif path == "/favicon.ico":
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Content-Length", str(len(FAVICON_SVG)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(FAVICON_SVG)
        elif path == "/api/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "has_env_api_key": bool((os.environ.get("GEMINI_API_KEY") or "").strip()),
                    "has_google_maps_key": bool((os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()),
                    "has_genai_sdk": HAS_GENAI,
                },
            )
        elif path == "/api/reverse-geocode":
            try:
                lat = float(params.get("lat", [""])[0])
                lon = float(params.get("lon", [""])[0])
                if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                    raise ValueError("out of bounds")
            except (TypeError, ValueError):
                self._send_json(400, {"detail": "Valid 'lat' and 'lon' query parameters are required."})
                return
            result = reverse_geocode_coordinates(lat, lon)
            self._send_json(200, result)
        elif path == "/api/environment":
            try:
                lat = float(params.get("lat", [""])[0])
                lon = float(params.get("lon", [""])[0])
                if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                    raise ValueError("out of bounds")
            except (TypeError, ValueError):
                self._send_json(400, {"detail": "Valid 'lat' and 'lon' query parameters are required."})
                return
            result = get_live_environment(lat, lon)
            self._send_json(200, result)
        elif path == "/api/geocode":
            q = (params.get("q", [""])[0] or "").strip()
            if not q:
                self._send_json(400, {"detail": "Query parameter 'q' is required."})
                return
            result = forward_geocode_query(q)
            if not result:
                self._send_json(404, {"detail": f"Location '{q}' not found."})
                return
            self._send_json(200, result)
        else:
            self._serve_static_safe(path)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/api/chat", "/api/routine-plan"):
            payload, err = self._read_json_body()
            if err:
                self._send_json(err[0], err[1])
                return
            if parsed.path == "/api/chat":
                status_code, response_data = handle_chat_logic(payload)
            else:
                status_code, response_data = handle_routine_logic(payload)
            self._send_json(status_code, response_data)
        else:
            self._send_json(404, {"detail": "Not found"})


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def create_server(host: str = "0.0.0.0", port: int = 8000) -> ReusableThreadingHTTPServer:
    """Create a configured threaded HTTP server instance."""
    return ReusableThreadingHTTPServer((host, port), VayuMitraHTTPRequestHandler)


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 8000))
    server = create_server(host, port)
    logger.info("VayuMitra AI is LIVE at http://localhost:%s (bound to %s:%s)", port, host, port)
    logger.info(
        "SDK Mode: %s | GEMINI_API_KEY configured: %s",
        "google-genai SDK" if HAS_GENAI else "REST fallback",
        "YES" if (os.environ.get("GEMINI_API_KEY") or "").strip() else "NO (demo fallback active)",
    )
    server.serve_forever()
