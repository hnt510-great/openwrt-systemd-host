#!/usr/bin/env python3
"""Run a bounded task on the existing Codex daemon, inheriting its default model."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time


class Connection:
    """Minimal RFC 6455 client over the daemon's private Unix socket."""

    def __init__(self, path, timeout):
        self.socket = socket.socket(socket.AF_UNIX)
        self.socket.settimeout(timeout)
        self.socket.connect(str(path))
        key = base64.b64encode(os.urandom(16)).decode()
        self.socket.sendall(('GET / HTTP/1.1\r\nHost: localhost\r\n'
            'Upgrade: websocket\r\nConnection: Upgrade\r\n'
            'Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: ' + key + '\r\n\r\n').encode())
        response = b''
        while not response.endswith(b'\r\n\r\n'):
            response += self.read(1)
            if len(response) > 16384:
                raise RuntimeError('Oversized WebSocket handshake')
        expected = base64.b64encode(hashlib.sha1(
            (key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
        if not response.startswith(b'HTTP/1.1 101 ') or expected.lower() not in response.lower():
            raise RuntimeError('Codex daemon rejected WebSocket handshake')

    def read(self, size):
        data = b''
        while len(data) < size:
            chunk = self.socket.recv(size - len(data))
            if not chunk:
                raise EOFError('Codex daemon disconnected')
            data += chunk
        return data

    def send(self, data, opcode=1):
        if not isinstance(data, bytes):
            data = json.dumps(data).encode()
        length = len(data)
        header = bytes([0x80 | opcode])
        header += (bytes([0x80 | length]) if length < 126 else
                   bytes([0x80 | 126]) + struct.pack('!H', length) if length < 65536 else
                   bytes([0x80 | 127]) + struct.pack('!Q', length))
        mask = os.urandom(4)
        self.socket.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def receive(self):
        fragments = b''
        while True:
            first, second = self.read(2)
            opcode, length = first & 15, second & 127
            if length == 126:
                length = struct.unpack('!H', self.read(2))[0]
            elif length == 127:
                length = struct.unpack('!Q', self.read(8))[0]
            if length > 16 * 1024 * 1024:
                raise RuntimeError('Oversized daemon message')
            mask = self.read(4) if second & 128 else None
            data = self.read(length)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if opcode == 8:
                raise EOFError('Codex daemon closed the connection')
            if opcode == 9:
                self.send(data, 10)
                continue
            if opcode == 10:
                continue
            fragments += data
            if first & 128:
                return json.loads(fragments)


def run_task(cwd, prompt, log, timeout=7200, read_only=False, extra_writable=()):
    status = json.loads(subprocess.check_output(
        ['codex', 'app-server', 'daemon', 'start'], text=True, timeout=60))
    connection = Connection(status['socketPath'], min(timeout, 60))
    deadline = time.monotonic() + timeout
    thread_id = turn_id = None
    counter = 0
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('a') as transcript:
        def receive():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Codex daemon task exceeded its time limit')
            connection.socket.settimeout(min(remaining, 60))
            while True:
                try:
                    message = connection.receive()
                    break
                except socket.timeout:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Codex daemon task exceeded its time limit')
            transcript.write(json.dumps(message) + '\n')
            transcript.flush()
            if 'method' in message and 'id' in message:
                # Unattended jobs cannot answer interactive tool/approval requests.
                connection.send({'id': message['id'], 'error': {
                    'code': -32000, 'message': 'Unattended task: interactive requests are disabled'}})
            return message

        def request(method, params):
            nonlocal counter
            counter += 1
            connection.send({'id': counter, 'method': method, 'params': params})
            while True:
                message = receive()
                if message.get('id') == counter and 'method' not in message:
                    if 'error' in message:
                        raise RuntimeError(json.dumps(message['error']))
                    return message['result']

        try:
            request('initialize', {'clientInfo': {
                'name': 'openwrt_scheduled_build', 'title': 'OpenWrt scheduled build', 'version': '1.0'}})
            connection.send({'method': 'initialized', 'params': {}})
            # Deliberately omit model, effort and serviceTier: inherit daemon defaults.
            thread = request('thread/start', {'cwd': str(cwd), 'approvalPolicy': 'never',
                'sandbox': 'read-only' if read_only else 'workspace-write',
                'config': {'sandbox_workspace_write.network_access': True}})
            thread_id = thread['thread']['id']
            # Git administration is read-only by default in workspace-write mode.
            # Grant only this workspace's Git directories explicitly.
            writable = [cwd, cwd / '.git', *extra_writable]
            writable += list((cwd / 'feeds').glob('*/.git'))
            writable += list((cwd / 'package').glob('*/.git'))
            started = request('turn/start', {'threadId': thread_id,
                'input': [{'type': 'text', 'text': prompt}],
                'sandboxPolicy': ({'type': 'readOnly', 'networkAccess': False} if read_only else
                    {'type': 'workspaceWrite', 'writableRoots': [str(p) for p in writable if p.exists()],
                     'networkAccess': True})})
            turn_id = started['turn']['id']
            while True:
                message = receive()
                params = message.get('params', {})
                if (message.get('method') == 'turn/completed' and params.get('threadId') == thread_id
                        and params['turn']['id'] == turn_id):
                    if params['turn']['status'] != 'completed':
                        raise RuntimeError('Codex task did not complete: ' + json.dumps(params['turn']))
                    return {'thread_id': thread_id, 'turn_id': turn_id,
                            'model': thread['model'], 'status': 'completed'}
        finally:
            if thread_id and turn_id:
                try:
                    connection.send({'id': 999999, 'method': 'turn/interrupt',
                                     'params': {'threadId': thread_id, 'turnId': turn_id}})
                except OSError:
                    pass
            connection.socket.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cwd', type=Path, required=True)
    parser.add_argument('--prompt', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=7200)
    parser.add_argument('--read-only', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run_task(args.cwd.resolve(), args.prompt.read_text(), args.log,
                              args.timeout, args.read_only), indent=2))
