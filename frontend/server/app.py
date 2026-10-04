"""Loopback HTTP transport. Run with the existing project virtual environment."""
from __future__ import annotations

import argparse
import gzip
import json
import math
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from frontend.server.serialization import ApiError, SCHEMA_VERSION, SCOPE, json_bytes
from frontend.server.service import LocatorService
from frontend.server.rediscovery import RediscoveryReader

MAX_BODY_BYTES = 64 * 1024


def accepts_gzip(value: str) -> bool:
    qualities = {}
    for entry in value.lower().split(","):
        encoding, *parameters = [part.strip() for part in entry.split(";")]
        quality = 1.0
        for parameter in parameters:
            if parameter.startswith("q="):
                try:
                    quality = float(parameter[2:])
                except ValueError:
                    quality = 0.0
                if not math.isfinite(quality) or not 0 <= quality <= 1:
                    quality = 0.0
        qualities[encoding] = quality
    return qualities.get("gzip", qualities.get("*", 0)) > 0


def make_handler(service):
    rediscovery = RediscoveryReader(getattr(service, "root", PROJECT_ROOT))

    class Handler(BaseHTTPRequestHandler):
        server_version = "LocatorLocalBridge/1.0"
        protocol_version = "HTTP/1.1"

        def setup(self):
            super().setup()
            self.connection.settimeout(20)

        def _origin(self):
            origin = self.headers.get("Origin")
            if not origin:
                return None
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ApiError("Only local browser origins may use the model bridge", 403, "origin_denied")
            return origin

        def _validate_host(self):
            try:
                host = urlsplit("//" + self.headers.get("Host", "")).hostname
            except ValueError:
                host = None
            if host not in {"localhost", "127.0.0.1", "::1"}:
                raise ApiError("This bridge accepts loopback requests only", 403, "host_denied")

        def _send(self, value, status=200, content_type="application/json; charset=utf-8", filename=None):
            body = value if isinstance(value, bytes) else json_bytes(value)
            compressible = content_type.startswith("application/json") and len(body) >= 1024
            compressed = compressible and accepts_gzip(self.headers.get("Accept-Encoding", ""))
            if compressed:
                body = gzip.compress(body, compresslevel=1, mtime=0)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            if compressed:
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            origin = self.headers.get("Origin")
            vary = ["Accept-Encoding"] if compressible else []
            if origin and urlsplit(origin).hostname in {"localhost", "127.0.0.1", "::1"}:
                self.send_header("Access-Control-Allow-Origin", origin)
                vary.append("Origin")
            if vary:
                self.send_header("Vary", ", ".join(vary))
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                self.close_connection = True

        def _handle(self, method):
            try:
                self._validate_host()
                self._origin()
                parts = urlsplit(self.path)
                if len(self.path) > 2048:
                    raise ApiError("Request URL exceeds the local API bound", 414, "url_size")
                path = [unquote(p) for p in parts.path.split("/") if p]
                query = parse_qs(parts.query, keep_blank_values=True)
                allowed_query = {"run_id", "boundary_year", "scenario"} if path == ["api", "socioeconomic"] else {"scenario", "run_id", "sublayer"}
                if any(len(v) != 1 for v in query.values()) or set(query) - allowed_query:
                    raise ApiError("Unknown or repeated query parameter")
                scenario = query.get("scenario", ["current"])[0]
                if method == "GET" and path == ["api", "capabilities"]:
                    return self._send(service.capabilities())
                if method == "POST" and path == ["api", "search"]:
                    if self.headers.get("Transfer-Encoding"):
                        raise ApiError("Chunked request bodies are unsupported")
                    try:
                        size = int(self.headers.get("Content-Length", "0"))
                    except ValueError as exc:
                        raise ApiError("Invalid content length") from exc
                    if size <= 0 or size > MAX_BODY_BYTES:
                        raise ApiError("Request body must be between 1 and 65536 bytes", 413, "body_size")
                    if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                        raise ApiError("Content-Type must be application/json", 415, "content_type")
                    try:
                        def reject_constant(value):
                            raise ValueError("Nonfinite JSON number")
                        def unique_keys(pairs):
                            result = {}
                            for key, value in pairs:
                                if key in result:
                                    raise ValueError("Duplicate JSON key")
                                result[key] = value
                            return result
                        body = json.loads(self.rfile.read(size).decode("utf-8"), parse_constant=reject_constant, object_pairs_hook=unique_keys)
                    except (ValueError, UnicodeDecodeError) as exc:
                        raise ApiError("Request must contain valid finite UTF-8 JSON") from exc
                    return self._send(service.search(body), 202)
                if method == "GET" and len(path) == 3 and path[:2] == ["api", "jobs"]:
                    return self._send(service.job(path[2]))
                if method == "GET" and len(path) == 3 and path[:2] == ["api", "runs"]:
                    return self._send(service.run_response(path[2], scenario))
                if method == "GET" and len(path) == 3 and path[:2] == ["api", "layers"]:
                    run_id = query.get("run_id", [None])[0]
                    if not run_id:
                        raise ApiError("run_id is required for layers")
                    return self._send(service.layer_result(path[2], run_id, scenario, query.get("sublayer", [None])[0]))
                if method == "GET" and path == ["api", "socioeconomic"]:
                    run_id = query.get("run_id", [None])[0]
                    if not run_id:
                        raise ApiError("run_id is required for county economic context")
                    return self._send(service.socioeconomic_result(run_id, query.get("boundary_year", ["2025"])[0], scenario))
                if method == "GET" and len(path) == 4 and path[:2] == ["api", "exports"]:
                    target = service.export(path[2], path[3], scenario)
                    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                    return self._send(target.read_bytes(), content_type=media_type, filename=target.name)
                if method == "GET" and path[:2] == ["api", "rediscovery"] and not query:
                    # Read-only post-hoc comparison with existing facilities; never a model input.
                    if len(path) == 2:
                        return self._send(rediscovery.index())
                    if len(path) == 3:
                        return self._send(rediscovery.payload_bytes(path[2]))
                    if len(path) == 4 and path[3] == "surface.png":
                        return self._send(rediscovery.surface(path[2]), content_type="image/png")
                if method == "GET" and path == ["api", "health"]:
                    return self._send({"schema_version": SCHEMA_VERSION, "status": "ready"})
                raise ApiError("Unknown API route", 404, "route_not_found")
            except ApiError as exc:
                self._send({"schema_version": SCHEMA_VERSION, "error": {"code": exc.code, "message": str(exc)}}, exc.status)
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                # A closed/stale browser never cancels or corrupts a queued scientific run.
                return
            except Exception as exc:
                self.log_error("%s: %s", type(exc).__name__, exc)
                self._send({"schema_version": SCHEMA_VERSION, "error": {"code": "bridge_error", "message": "The local model bridge could not read this output; check its terminal diagnostics"}}, 500)

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def do_OPTIONS(self):
            try:
                self._validate_host()
                self._origin()
                self.send_response(204)
                self.send_header("Content-Length", "0")
                origin = self.headers.get("Origin")
                if origin:
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()
            except ApiError as exc:
                self._send({"schema_version": SCHEMA_VERSION, "error": {"code": exc.code, "message": str(exc)}}, exc.status)
    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description="Serve the local accepted deterministic model API on loopback")
    parser.add_argument("--port", type=int, default=8787, help="Loopback port (default: 8787)")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be 1–65535")
    service = LocatorService(PROJECT_ROOT)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(service))
    server.daemon_threads = True
    print(f"Locator model bridge ready at http://127.0.0.1:{args.port}; {SCOPE}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
