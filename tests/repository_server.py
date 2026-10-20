"""Serve controlled NuGet V3 responses without external network access."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class RepositoryServer:
    """Keep response bodies and record every requested resource path."""

    def __init__(self):
        """Start an isolated HTTP server on an available loopback port."""
        self.routes = {}
        self.requests = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            """Return fixture bytes, or a 404 for unexpected requests."""

            def do_GET(self):
                """Record and answer one GET request."""
                owner.requests.append(self.path)
                status, body = owner.routes.get(self.path, (404, b"missing"))
                self.send_response(status)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                """Suppress HTTP logging in test output."""

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.set_index()

    def set_index(self):
        """Advertise a custom content URL to check service discovery."""
        index = {"resources": [{
            "@type": "PackageBaseAddress/3.0.0",
            "@id": self.url + "/content/",
        }]}
        self.routes["/v3/index.json"] = (200, json.dumps(index).encode())

    def close(self):
        """Stop the server and release its socket."""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
