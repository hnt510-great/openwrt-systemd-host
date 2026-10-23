#!/usr/bin/env python3
"""Exercise packaged Firefox in a temporary ordinary-user Wayland profile.

Run with a directory containing h264.mp4, vp9.webm and av1.webm. This uses
Marionette only in the disposable profile; it never edits a normal profile.
Decoder logs and about:support data are evidence, not a GPU-success assertion.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import signal
import shutil
import socket
import subprocess
import tempfile
import time


class Marionette:
    def __init__(self, port, process):
        deadline = time.monotonic() + 45
        while True:
            try:
                self.sock = socket.create_connection(('127.0.0.1', port), 2)
                break
            except OSError:
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('Firefox Marionette did not start')
                time.sleep(.2)
        self.sock.settimeout(45)
        self.receive()
        self.sequence = 0
        self.call('WebDriver:NewSession', {'capabilities': {}})

    def receive(self):
        size = b''
        while not size.endswith(b':'):
            chunk = self.sock.recv(1)
            if not chunk:
                raise RuntimeError('Marionette closed the connection')
            size += chunk
        remaining = int(size[:-1])
        data = b''
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise RuntimeError('Truncated Marionette packet')
            data += chunk
            remaining -= len(chunk)
        return json.loads(data)

    def call(self, name, args=None):
        self.sequence += 1
        packet = json.dumps([0, self.sequence, name, args or {}]).encode()
        self.sock.sendall(str(len(packet)).encode() + b':' + packet)
        response = self.receive()
        assert response[:2] == [1, self.sequence], response
        if response[2]:
            raise RuntimeError(f'{name}: {response[2]}')
        return response[3]

    def script(self, script, args=None, asynchronous=False):
        value = self.call('WebDriver:ExecuteAsyncScript' if asynchronous else
                          'WebDriver:ExecuteScript',
                          {'script': script, 'args': args or [],
                           'newSandbox': False, 'sandbox': 'default'})
        return value.get('value', value) if isinstance(value, dict) else value


def video_state(client):
    return client.script('''
        const v = document.querySelector('video');
        const q = v.getVideoPlaybackQuality();
        return {time: v.currentTime, paused: v.paused, ready: v.readyState,
                width: v.videoWidth, height: v.videoHeight,
                frames: q.totalVideoFrames, dropped: q.droppedVideoFrames,
                error: v.error && {code: v.error.code, message: v.error.message}};
    ''')


def process_sandboxes(parent):
    processes = {}
    for path in Path('/proc').glob('[0-9]*/status'):
        try:
            status = dict(line.split(':', 1) for line in path.read_text().splitlines())
            if int(status['Uid'].split()[0]) == os.getuid():
                processes[int(path.parent.name)] = status
        except (OSError, KeyError, ValueError):
            continue
    selected = {parent}
    while True:
        children = {pid for pid, status in processes.items()
                    if int(status['PPid'].strip()) in selected}
        if children.issubset(selected):
            break
        selected.update(children)
    result = []
    for pid in sorted(selected):
        if pid not in processes:
            continue
        status = processes[pid]
        result.append(dict(pid=pid, **{
            key: status.get(key, '').strip()
            for key in ['Name', 'PPid', 'Seccomp', 'NoNewPrivs', 'CapEff']}))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('media', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if os.getuid() == 0:
        parser.error('Run as the ordinary desktop user')
    args.media = args.media.resolve()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    for name in ['h264.mp4', 'vp9.webm', 'av1.webm']:
        if not (args.media / name).is_file():
            parser.error('Missing media sample: ' + name)

    with tempfile.TemporaryDirectory(prefix='firefox-vaapi-profile-') as profile:
        for name in ['h264.mp4', 'vp9.webm', 'av1.webm']:
            shutil.copyfile(args.media / name, Path(profile, name))
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        Path(profile, 'user.js').write_text(
            f'user_pref("marionette.port", {port});\n'
            'user_pref("browser.shell.checkDefaultBrowser", false);\n'
            'user_pref("browser.startup.homepage_override.mstone", "ignore");\n'
            'user_pref("browser.aboutwelcome.enabled", false);\n')
        page = Path(profile, 'video.html')
        page.write_text('''<!doctype html><meta charset="utf-8">
            <title>Firefox VA-API validation</title>
            <video muted loop controls width="960"></video>
            <button id="fullscreen" onclick="document.querySelector('video').requestFullscreen()">Fullscreen</button>
            ''')
        environment = os.environ.copy()
        # Crash-helper logs and toolkit caches can live outside --profile.
        # Keep those shared application directories disposable as well.
        for variable, directory in [('XDG_CONFIG_HOME', 'config'),
                                    ('XDG_CACHE_HOME', 'cache'),
                                    ('XDG_DATA_HOME', 'data'),
                                    ('XDG_STATE_HOME', 'state')]:
            isolated = Path(profile, directory)
            isolated.mkdir()
            environment[variable] = str(isolated)
        environment.update(MOZ_LOG='timestamp,PlatformDecoderModule:4,FFmpegVideo:5',
                           MOZ_LOG_FILE=str(args.output / 'decoder.log'))
        report = {'uid': os.getuid(), 'wayland': environment.get('WAYLAND_DISPLAY'),
                  'samples': {}, 'started': time.time()}
        log = (args.output / 'browser.log').open('w')
        process = subprocess.Popen(
            ['/usr/bin/firefox-esr', '--no-remote', '--profile', profile,
             '--marionette', '--remote-allow-system-access', 'about:blank'],
            env=environment, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True)
        report['pid'] = process.pid
        client = None
        try:
            client = Marionette(port, process)
            client.call('WebDriver:SetTimeouts', {'script': 30000})
            client.call('WebDriver:Navigate', {'url': page.as_uri()})
            for name in ['h264.mp4', 'vp9.webm', 'av1.webm']:
                item = {'started': time.time()}
                client.script('''
                    const v = document.querySelector('video');
                    v.src = arguments[0]; v.muted = true; v.play();
                ''', [Path(profile, name).as_uri()])
                deadline = time.monotonic() + 30
                while True:
                    before = video_state(client)
                    if before['error']:
                        raise RuntimeError(f'{name}: {before}')
                    if before['frames'] > 2 and before['time'] > .2:
                        break
                    if time.monotonic() > deadline:
                        raise RuntimeError(f'{name}: no decoded video: {before}')
                    time.sleep(.25)
                time.sleep(3)
                after = video_state(client)
                assert after['frames'] > before['frames'], (name, before, after)
                assert after['width'] > 0 and not after['error'], after
                item.update(before=before, playing=after)
                item['process_sandboxes'] = process_sandboxes(process.pid)
                screenshot = client.call('WebDriver:TakeScreenshot',
                                         {'id': None, 'highlights': [], 'full': False})
                screenshot = screenshot.get('value', screenshot)
                (args.output / (name + '.png')).write_bytes(base64.b64decode(screenshot))
                client.script("document.querySelector('video').pause()")
                paused = video_state(client)
                time.sleep(.5)
                stopped = video_state(client)
                assert abs(stopped['time'] - paused['time']) < .1, stopped
                client.script("document.querySelector('video').currentTime = 1.5")
                time.sleep(.5)
                sought = video_state(client)
                assert abs(sought['time'] - 1.5) < .3, sought
                client.script("document.querySelector('video').play()")
                time.sleep(1)
                resumed = video_state(client)
                assert resumed['frames'] > sought['frames'], resumed
                item.update(paused=stopped, sought=sought, resumed=resumed)
                if name == 'h264.mp4':
                    element = client.call('WebDriver:FindElement',
                                          {'using': 'css selector', 'value': '#fullscreen'})
                    element = element.get('value', element)
                    element_id = next(iter(element.values()))
                    client.call('WebDriver:ElementClick', {'id': element_id})
                    time.sleep(.5)
                    item['fullscreen'] = client.script('return !!document.fullscreenElement')
                    assert item['fullscreen'], 'Fullscreen did not activate'
                    client.script('document.exitFullscreen()')
                client.script("document.querySelector('video').pause()")
                report['samples'][name] = item
            client.call('Marionette:SetContext', {'value': 'chrome'})
            report['support'] = client.script('''
                const done = arguments[arguments.length - 1];
                const {Troubleshoot} = ChromeUtils.importESModule(
                    'resource://gre/modules/Troubleshoot.sys.mjs');
                Troubleshoot.snapshot().then(done, e => done({error: String(e)}));
            ''', asynchronous=True)
            report['passed'] = True
        except Exception as error:
            report['error'] = str(error)
            raise
        finally:
            report['finished'] = time.time()
            (args.output / 'result.json').write_text(json.dumps(report, indent=2))
            if client:
                try:
                    client.call('WebDriver:DeleteSession')
                except Exception:
                    pass
                client.sock.close()
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            log.close()
    print(json.dumps({'passed': report['passed'], 'output': str(args.output)}))


if __name__ == '__main__':
    main()
