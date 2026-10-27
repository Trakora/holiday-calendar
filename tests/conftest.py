"""Serves tests/fixture over HTTP, with Range support like data.trakora.com, so every client
runs against real URLs. The fixture holds two small releases (2026, then 2027)."""

import functools
import json
import re
import shutil
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixture"


class RangeHandler(SimpleHTTPRequestHandler):
    """DuckDB reads Parquet over HTTP in byte ranges; the standard handler ignores them."""

    def send_head(self):
        match = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
        path = Path(self.translate_path(self.path))
        if not match or not path.is_file():
            return super().send_head()
        size = path.stat().st_size
        start = int(match[1])
        end = min(int(match[2]) if match[2] else size - 1, size - 1)
        f = path.open("rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.range_remaining = end - start + 1
        return f

    def copyfile(self, source, outputfile):
        remaining = getattr(self, "range_remaining", None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        outputfile.write(source.read(remaining))

    def end_headers(self):
        if self.command == "HEAD" or "Range" not in self.headers:
            self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def serve():
    """serve(directory) -> base URL of the holiday calendar inside that directory."""
    servers = []

    def start(directory: Path) -> str:
        handler = functools.partial(RangeHandler, directory=str(directory))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}/holiday-calendar/v1"

    yield start
    for server in servers:
        server.shutdown()


@pytest.fixture(scope="session")
def base_url(serve):
    return serve(FIXTURE)


@pytest.fixture
def first_release_only(tmp_path):
    """A copy of the fixture whose manifest only knows the first release."""
    copy = tmp_path / "published"
    shutil.copytree(FIXTURE, copy)
    manifest_path = copy / "holiday-calendar" / "v1" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["releases"] = manifest["releases"][:1]
    manifest["release_seq"] = 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return copy
