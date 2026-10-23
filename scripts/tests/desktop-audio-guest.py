#!/usr/bin/env python3
"""Run audio signal checks inside a disposable native-systemd desktop guest."""
import argparse
import array
import json
import math
import os
from pathlib import Path
import pwd
import signal
import socket
import subprocess
import time
import wave


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--firefox', action='store_true')
    args = parser.parse_args()
    account = pwd.getpwnam(args.user)
    assert os.getuid() == 0 and account.pw_uid >= 1000
    args.output.mkdir(parents=True, exist_ok=True)
    os.chown(args.output, account.pw_uid, account.pw_gid)
    runtime = Path('/run/user') / str(account.pw_uid)
    env = dict(os.environ, HOME=account.pw_dir, USER=args.user, LOGNAME=args.user,
               XDG_RUNTIME_DIR=str(runtime), DBUS_SESSION_BUS_ADDRESS='unix:path=' + str(runtime / 'bus'),
               PULSE_SERVER='unix:' + str(runtime / 'pulse/native'))
    child = dict(env=env, user=account.pw_uid, group=account.pw_gid,
                 extra_groups=os.getgrouplist(args.user, account.pw_gid))
    results = {}

    def run(command, **kwargs):
        return subprocess.run(command, check=True, capture_output=True, text=True,
                              timeout=30, **child, **kwargs)

    def inspect_signal(path):
        data = array.array('h')
        data.frombytes(path.read_bytes()[:path.stat().st_size // 4 * 4])
        peak = max(map(abs, data), default=0)
        rms = math.sqrt(sum(x * x for x in data) / max(1, len(data)))
        assert peak > 100 and rms > 20, (path.name, len(data), peak, rms)
        return {'samples': len(data), 'peak': peak, 'rms': rms}

    def capture_playback(name, command, duration=None, ready=None):
        path = args.output / (name + '.raw')
        with path.open('wb') as output, (args.output / (name + '.log')).open('wb') as log:
            recorder = subprocess.Popen(['parec', '--device=@DEFAULT_MONITOR@', '--raw',
                                         '--format=s16le', '--rate=48000', '--channels=2',
                                         '--latency-msec=20'], stdout=output, stderr=log, **child)
            player = None
            try:
                time.sleep(.4)
                player = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                          start_new_session=True, **child)
                if ready:
                    ready(player)
                if duration:
                    time.sleep(duration)
                else:
                    assert player.wait(timeout=30) == 0, name
                time.sleep(.2)
            finally:
                if player is not None and player.poll() is None:
                    os.killpg(player.pid, signal.SIGTERM)
                    player.wait(timeout=15)
                recorder.terminate()
                recorder.wait(timeout=10)
        return inspect_signal(path)

    results['pulse'] = run(['pactl', 'info']).stdout
    results['wireplumber'] = run(['wpctl', 'status', '-n']).stdout
    graph = json.loads(run(['pw-dump']).stdout)
    results['alsa_devices'] = [item['info']['props'].get('device.name') for item in graph
                               if item.get('info', {}).get('props', {}).get('device.api') == 'alsa']
    assert results['alsa_devices'], 'ALSA hardware was not discovered'
    run(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', '0'])
    run(['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', '0.5'])
    results['pipewire_playback'] = capture_playback('pw-play', ['pw-play', str(args.fixtures / 'tone.wav')])
    results['alsa_playback'] = capture_playback('aplay', ['aplay', '-q', str(args.fixtures / 'tone.wav')])
    results['codecs'] = {}
    for filename in ['tone.wav', 'tone.mp3', 'tone.aac', 'tone.opus', 'tone.ogg', 'tone.flac']:
        results['codecs'][filename] = capture_playback(filename, [
            'gst-launch-1.0', '-q', 'filesrc', 'location=' + str(args.fixtures / filename),
            '!', 'decodebin', '!', 'audioconvert', '!', 'audioresample', '!', 'pulsesink'])
    recording = args.output / 'alsa-recording.wav'
    run(['arecord', '-q', '-f', 'S16_LE', '-r', '48000', '-c', '2', '-d', '1', str(recording)])
    with wave.open(str(recording), 'rb') as audio:
        assert audio.getnframes() >= 47000
        results['alsa_recording'] = {'frames': audio.getnframes(), 'rate': audio.getframerate()}
    if args.firefox:
        sockets = list(runtime.glob('wayland-*'))
        sockets = [p for p in sockets if p.is_socket()]
        assert sockets, 'No active Wayland desktop'
        env.update(WAYLAND_DISPLAY=sockets[0].name, MOZ_ENABLE_WAYLAND='1', GDK_BACKEND='wayland',
                   MOZ_LOG='cubeb:5', MOZ_LOG_FILE=str(args.output / 'firefox-cubeb'))
        profile = args.output / 'firefox-profile'
        profile.mkdir(exist_ok=True)
        os.chown(profile, account.pw_uid, account.pw_gid)
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        prefs = profile / 'user.js'
        prefs.write_text(f'user_pref("marionette.port", {port});\n'
                         'user_pref("browser.aboutwelcome.enabled", false);\n'
                         'user_pref("browser.startup.homepage_override.mstone", "ignore");\n'
                         'user_pref("browser.shell.checkDefaultBrowser", false);\n')
        os.chown(prefs, account.pw_uid, account.pw_gid)

        def start_browser_audio(player):
            client = Marionette(port, player)
            try:
                client.script("document.body.innerHTML='<button id=play>Play tone</button>';"
                              "document.querySelector('button').onclick=()=>{"
                              "window.a=new AudioContext();window.o=a.createOscillator();"
                              "o.frequency.value=997;o.connect(a.destination);o.start();a.resume();};")
                element = client.call('WebDriver:FindElement', {'using': 'css selector', 'value': '#play'})
                element = element.get('value', element)
                element_id = element.get('element-6066-11e4-a52e-4f735466cecf', element.get('ELEMENT'))
                client.call('WebDriver:ElementClick', {'id': element_id})
                time.sleep(.5)
                results['firefox_context'] = client.script('return {state:a.state, rate:a.sampleRate};')
                assert results['firefox_context']['state'] == 'running'
            finally:
                client.sock.close()

        results['firefox'] = capture_playback('firefox', ['firefox-esr', '--no-remote',
                                                        '--profile', str(profile), '--marionette',
                                                        'about:blank'], duration=4, ready=start_browser_audio)
    (args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
