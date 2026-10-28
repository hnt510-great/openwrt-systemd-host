#!/usr/bin/env python3
"""Run an isolated RDP audio client environment without physical audio devices.

The output directory must be new. client-env.json supplies environment values
for FreeRDP, ffmpeg and other client processes. Received playback goes to
rdp-playback; play tone.wav into rdp-microphone to inject a microphone signal.
Send {"quit": true} on stdin to stop the fixture's own processes.
"""
import argparse
import array
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import wave


def private_environment(out, runtime):
    env = dict(os.environ, HOME=str(out / 'home'), XDG_RUNTIME_DIR=str(runtime),
               PIPEWIRE_RUNTIME_DIR=str(runtime),
               XDG_CONFIG_HOME=str(out / 'config'), XDG_DATA_HOME=str(out / 'data'),
               XDG_STATE_HOME=str(out / 'state'), XDG_CACHE_HOME=str(out / 'cache'),
               GIO_USE_VFS='local', PULSE_RUNTIME_PATH=str(runtime / 'pulse'),
               PULSE_SERVER='unix:' + str(runtime / 'pulse/native'),
               PULSE_SINK='rdp-playback', PULSE_SOURCE='rdp-microphone.monitor')
    for name in ['DISPLAY', 'WAYLAND_DISPLAY', 'PIPEWIRE_REMOTE']:
        env.pop(name, None)
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--private-bus', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--runtime', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    os.umask(0o077)
    out = args.out.resolve()
    if not args.private_bus:
        out.mkdir(parents=True, mode=0o700)
        for name in ['home', 'config', 'data', 'state', 'cache']:
            (out / name).mkdir(mode=0o700)
        # Unix socket paths are limited to 108 bytes, regardless of output path.
        runtime = Path(tempfile.mkdtemp(prefix='gnome-client-audio-', dir='/tmp'))
        command = ['dbus-run-session', '--', sys.executable, str(Path(__file__).resolve()),
                   '--out', str(out), '--runtime', str(runtime), '--private-bus']
        if args.self_test:
            command.append('--self-test')
        try:
            # D-Bus-activated helpers must receive the same private environment.
            return subprocess.call(command, env=private_environment(out, runtime))
        finally:
            shutil.rmtree(runtime)
    if args.runtime is None:
        parser.error('--runtime is required for the private child')
    runtime = args.runtime
    env = private_environment(out, runtime)
    config = out / 'config/pipewire/pipewire-pulse.conf.d'
    config.mkdir(parents=True)
    (config / '10-test.conf').write_text('''pulse.cmd = [
  { cmd = "load-module" args = "module-null-sink sink_name=rdp-playback rate=48000 channels=2" }
  { cmd = "load-module" args = "module-null-sink sink_name=rdp-microphone rate=48000 channels=2" }
]
''')
    processes, logs = [], []

    def start(command, name):
        log = (out / (name + '.log')).open('wb')
        logs.append(log)
        process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        processes.append(process)
        return process

    def wait_socket(path):
        deadline = time.monotonic() + 15
        while not path.is_socket():
            if any(p.poll() is not None for p in processes) or time.monotonic() > deadline:
                raise RuntimeError(f'Private audio startup failed: {path.name}')
            time.sleep(.1)

    try:
        start(['pipewire'], 'pipewire')
        wait_socket(runtime / 'pipewire-0')
        # The policy profile has no ALSA, Bluetooth or camera monitors.
        start(['wireplumber', '--profile=policy'], 'wireplumber')
        start(['pipewire-pulse'], 'pulse')
        wait_socket(runtime / 'pulse/native')
        environment = {key: env[key] for key in [
            'HOME', 'XDG_RUNTIME_DIR', 'PIPEWIRE_RUNTIME_DIR', 'XDG_CONFIG_HOME',
            'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME', 'PULSE_RUNTIME_PATH',
            'PULSE_SERVER', 'PULSE_SINK', 'PULSE_SOURCE', 'DBUS_SESSION_BUS_ADDRESS',
            'GIO_USE_VFS']}
        (out / 'client-env.json').write_text(json.dumps(environment, indent=2) + '\n')
        signal = array.array('h', (int(4000 * math.sin(2 * math.pi * 1000 * i / 48000))
                                   for i in range(96000) for _ in range(2)))
        with wave.open(str(out / 'tone.wav'), 'wb') as stream:
            stream.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
            stream.writeframes(signal.tobytes())
        if args.self_test:
            time.sleep(1)
            objects = json.loads(subprocess.check_output(['pw-dump'], env=env, text=True))
            hardware = [o for o in objects if o.get('info', {}).get('props', {}).get(
                'device.api') in ['alsa', 'bluez5', 'v4l2', 'libcamera']]
            if hardware:
                raise RuntimeError('Physical devices appeared in the private audio graph')
            (out / 'objects.json').write_text(json.dumps(objects, indent=2) + '\n')
            recorder = start(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                              '-f', 'pulse', '-i', 'rdp-playback.monitor', '-t', '3',
                              '-ac', '2', '-ar', '48000', '-f', 's16le',
                              str(out / 'received.raw')], 'recorder')
            time.sleep(.5)
            subprocess.run(['pw-play', '--target=rdp-playback', str(out / 'tone.wav')],
                           env=env, check=True, timeout=10, capture_output=True)
            recorder.wait(timeout=10)
            if recorder.returncode:
                raise RuntimeError('Private audio recorder failed')
            data = array.array('h')
            data.frombytes((out / 'received.raw').read_bytes())
            peak = max(map(abs, data), default=0)
            rms = math.sqrt(sum(x * x for x in data) / max(1, len(data)))
            if peak <= 100 or rms <= 20:
                raise RuntimeError('Private playback signal is silent')
            def power(frequency):
                coefficient = 2 * math.cos(2 * math.pi * frequency / 48000)
                previous = before = 0.0
                for sample in data[::2]:
                    value = sample + coefficient * previous - before
                    before, previous = previous, value
                return previous * previous + before * before - coefficient * previous * before
            ratio = power(1000) / max(1, power(500), power(1500))
            if ratio < 100:
                raise RuntimeError('Recorded signal does not match the 1000 Hz fixture')
            result = dict(peak=peak, rms=rms, samples=len(data), dominant_hz=1000,
                          tone_power_ratio=ratio, physical_devices=len(hardware))
            (out / 'self-test.json').write_text(json.dumps(result, indent=2) + '\n')
            print(json.dumps(result), flush=True)
        else:
            print(json.dumps({'ready': True, 'environment': str(out / 'client-env.json'),
                              'tone': str(out / 'tone.wav')}), flush=True)
            for line in sys.stdin:
                if json.loads(line).get('quit'):
                    break
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError('A private audio process exited')
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        for log in logs:
            log.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
