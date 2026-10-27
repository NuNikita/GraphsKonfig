"""Serve controlled NuGet V3 responses without external network access."""

import json
import threading
from http import HTTPStatus
from wsgiref.simple_server import WSGIRequestHandler, make_server


class QuietRequestHandler(WSGIRequestHandler):
    """Keep the standard WSGI handler without HTTP logging in tests."""

    def log_message(self, *args):
        """Suppress HTTP logging in test output."""


class RepositoryServer:
    """Keep response bodies and record every requested resource path."""

    def __init__(self):
        """Start an isolated HTTP server on an available loopback port."""
        self.routes = {}
        self.requests = []
        self.server = make_server(
            "127.0.0.1", 0, self.handle_request,
            handler_class=QuietRequestHandler,
        )
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.set_index()
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def handle_request(self, environ, start_response):
        """Record a WSGI request and return fixture bytes or HTTP 404."""
        path = environ["PATH_INFO"]
        if environ.get("QUERY_STRING"):
            path += "?" + environ["QUERY_STRING"]
        self.requests.append(path)
        status, body = self.routes.get(path, (404, b"missing"))
        status_line = f"{status} {HTTPStatus(status).phrase}"
        start_response(status_line, [("Content-Length", str(len(body)))])
        return [body]

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
