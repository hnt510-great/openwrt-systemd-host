#!/usr/bin/env python3
"""Serve published APK snapshots to a specified LAN, with no directory listings."""
import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Handler(SimpleHTTPRequestHandler):
    def list_directory(self, path):
        self.send_error(403, 'Directory listing disabled')

    def send_head(self):
        if ipaddress.ip_address(self.client_address[0]) not in self.server.lan:
            self.send_error(403, 'LAN clients only')
            return None
        path = unquote(urlsplit(self.path).path)
        candidate = (self.server.root / path.lstrip('/')).resolve()
        if not candidate.is_relative_to(self.server.root) or not (
                candidate.name.endswith('.apk') or candidate.name in
                ('packages.adb', 'manifest.json', 'repositories.list')):
            self.send_error(403, 'Published feed files only')
            return None
        return super().send_head()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', required=True)
    parser.add_argument('--port', type=int, default=8088)
    parser.add_argument('--lan', required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    root = args.directory.resolve(strict=True)
    server = ThreadingHTTPServer((args.bind, args.port), functools.partial(Handler, directory=str(root)))
    server.root = root
    server.lan = ipaddress.ip_network(args.lan)
    server.serve_forever()


if __name__ == '__main__':
    main()
