#!/usr/bin/env python3
"""Exercise the real nginx feed configuration without touching live feeds."""
import http.client
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
NGINX = shutil.which('nginx') or '/usr/sbin/nginx'


@unittest.skipUnless(Path(NGINX).is_file(), 'nginx is required')
class FeedServerTest(unittest.TestCase):
    def test_feed_access_and_publication(self):
        with tempfile.TemporaryDirectory(prefix='apk-nginx-') as directory:
            base = Path(directory)
            public = base / 'public'
            for name, data in [('old', b'old index'), ('new', b'new index')]:
                snapshot = public / name
                snapshot.mkdir(parents=True)
                for filename in ('packages.adb', 'test.apk', 'manifest.json', 'repositories.list'):
                    (snapshot / filename).write_bytes(data)
                (snapshot / 'private-key.pem').write_text('forbidden')
                (snapshot / '.hidden.apk').write_text('forbidden')
            images = public / 'images/7.3-g38-0123456789abcdef'
            images.mkdir(parents=True)
            image_files = ('openwrt-test.img.gz', 'SHA256SUMS', 'SHA256SUMS.sig',
                           'image-signing.pub.pem')
            for filename in (*image_files, 'private-key.pem', 'unapproved.img'):
                (images / filename).write_bytes(b'image fixture')
            (public / 'abi').mkdir()
            alias = public / 'abi/kernel'
            alias.symlink_to('../old')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            config = (ROOT / 'configs/lan-apk-feeds.nginx.conf').read_text()
            config = config.replace('/run/lan-apk-feeds', str(base / 'run'))
            config = config.replace('/srv/openwrt-feeds/public', str(public))
            config = config.replace('192.0.2.165:8088', f'127.0.0.1:{port}')
            config = config.replace('allow 192.0.2.0/24;', 'allow 127.0.0.1;')
            config = config.replace('worker_processes auto;', 'worker_processes 1;')
            (base / 'run').mkdir()
            conf = base / 'nginx.conf'
            conf.write_text(config)
            subprocess.run([NGINX, '-t', '-c', str(conf)], check=True, capture_output=True)
            with (base / 'log').open('w') as log:
                proc = subprocess.Popen([NGINX, '-c', str(conf)], stdout=log, stderr=log)
                try:
                    for _ in range(100):
                        try:
                            with socket.create_connection(('127.0.0.1', port), timeout=.1):
                                break
                        except OSError:
                            if proc.poll() is not None:
                                self.fail((base / 'log').read_text())
                            time.sleep(.02)
                    def request(path, method='GET', headers=None, source=None):
                        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=3,
                                                         source_address=source)
                        conn.request(method, path, headers=headers or {})
                        response = conn.getresponse()
                        result = response.status, dict(response.getheaders()), response.read()
                        conn.close()
                        return result
                    for filename in ('packages.adb', 'test.apk', 'manifest.json', 'repositories.list'):
                        status, headers, body = request('/abi/kernel/' + filename)
                        self.assertEqual((status, body), (200, b'old index'))
                        self.assertEqual(headers['Cache-Control'], 'no-cache')
                        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
                    self.assertEqual(request('/abi/kernel/test.apk', 'HEAD')[2], b'')
                    status, _, body = request('/abi/kernel/test.apk', headers={'Range': 'bytes=0-2'})
                    self.assertEqual((status, body), (206, b'old'))
                    for path in ('/', '/abi/kernel/', '/private-key.pem',
                                 '/abi/kernel/private-key.pem', '/abi/kernel/.hidden.apk',
                                 '/abi/kernel/%2ehidden.apk', '/../../etc/passwd'):
                        self.assertIn(request(path)[0], (400, 403))
                    self.assertEqual(request('/abi/kernel/missing.apk')[0], 404)
                    self.assertEqual(request('/abi/kernel/test.apk', 'POST')[0], 403)
                    self.assertEqual(request('/abi/kernel/test.apk', source=('127.0.0.2', 0))[0], 403)
                    for filename in image_files:
                        path = '/images/7.3-g38-0123456789abcdef/' + filename
                        self.assertEqual(request(path)[::2], (200, b'image fixture'))
                        self.assertEqual(request(path, 'HEAD')[0], 200)
                        self.assertEqual(request(path, 'POST')[0], 403)
                        self.assertEqual(request(path, source=('127.0.0.2', 0))[0], 403)
                    for filename in ('private-key.pem', 'unapproved.img', ''):
                        self.assertEqual(request('/images/7.3-g38-0123456789abcdef/' + filename)[0], 403)
                    replacement = public / 'abi/next'
                    replacement.symlink_to('../new')
                    replacement.replace(alias)
                    self.assertEqual(request('/abi/kernel/packages.adb')[2], b'new index')
                finally:
                    proc.terminate()
                    proc.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
