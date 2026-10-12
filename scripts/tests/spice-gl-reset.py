#!/usr/bin/python3
"""Exercise SPICE pending-draw resets and input teardown in a disposable VM.

Requires target SpiceClientGLib GI, a bootable test kernel/initramfs and KVM.
Only the new QEMU process and files in a temporary directory are modified.
"""
import argparse
import json
import resource
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import gi

gi.require_version('SpiceClientGLib', '2.0')
from gi.repository import GLib, GObject, SpiceClientGLib as Spice

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--qemu', default='/usr/bin/qemu-system-x86_64')
parser.add_argument('--kernel', required=True)
parser.add_argument('--initrd', required=True)
parser.add_argument('--data-dir', default='/usr/share/qemu')
parser.add_argument('--rendernode', default='/dev/dri/renderD128')
parser.add_argument('--video', choices=['gl', 'qxl'], default='gl')
parser.add_argument('--resets', type=int, default=3)
parser.add_argument('--duration', type=int, default=25)
args = parser.parse_args()
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

with tempfile.TemporaryDirectory(prefix='spice-regression-') as directory:
    work = Path(directory)
    disk = work / 'test.raw'
    with disk.open('wb') as stream:
        stream.truncate(32 * 1024 * 1024)
    logpath = work / 'qemu.log'
    serialpath = work / 'serial.log'
    command = [
        args.qemu, '-L', args.data_dir, '-name', 'spice-regression-disposable',
        '-machine', 'q35,accel=kvm', '-cpu', 'host', '-m', '512', '-smp', '1',
        '-nodefaults', '-no-shutdown', '-display', 'none',
        '-device', 'qemu-xhci', '-device', 'usb-tablet',
        '-device', 'virtio-vga-gl' if args.video == 'gl' else 'qxl-vga',
        '-spice', 'unix=on,addr=' + str(work / 'spice.sock') +
        ',disable-ticketing=on' +
        (',gl=on,rendernode=' + args.rendernode if args.video == 'gl' else ''),
        '-kernel', args.kernel, '-initrd', args.initrd,
        '-append', 'console=ttyS0 rdinit=/init panic=0',
        '-serial', 'file:' + str(serialpath),
        '-drive', 'if=virtio,format=raw,file=' + str(disk),
        '-qmp', 'unix:' + str(work / 'qmp.sock') + ',server=on,wait=off',
    ]
    logfile = logpath.open('wb')
    process = subprocess.Popen(command, stdout=logfile, stderr=logfile)
    loop = GLib.MainLoop()
    channels = []
    counts = {'draws': 0, 'acks': 0, 'scanouts': 0, 'resets': 0, 'inputs': 0}
    qmp = None
    replies = None
    session = None
    result = 1
    try:
        deadline = time.monotonic() + 10
        while not (work / 'qmp.sock').exists():
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Test QEMU failed to create its QMP socket')
            time.sleep(.05)
        qmp = socket.socket(socket.AF_UNIX)
        qmp.connect(str(work / 'qmp.sock'))
        qmp.settimeout(5)
        replies = qmp.makefile('rb')
        replies.readline()

        def execute(name):
            qmp.sendall(json.dumps({'execute': name}).encode() + b'\n')
            while True:
                data = replies.readline()
                if not data:
                    raise RuntimeError('Test QEMU closed QMP')
                reply = json.loads(data)
                if 'return' in reply:
                    return reply['return']
                if 'error' in reply:
                    raise RuntimeError(reply)

        execute('qmp_capabilities')
        session = Spice.Session()
        session.set_property('unix-path', str(work / 'spice.sock'))
        session.set_property('gl-scanout', True)

        def acknowledge(channel):
            if process.poll() is None:
                channel.gl_draw_done()
                counts['acks'] += 1
            return False

        def draw(channel, x, y, width, height):
            counts['draws'] += 1
            if counts['resets'] < args.resets and counts['draws'] % 10 == 1:
                print('RESET_WITH_UNACKNOWLEDGED_DRAW', counts['resets'] + 1,
                      width, height, flush=True)
                try:
                    execute('system_reset')
                    counts['resets'] += 1
                except (OSError, RuntimeError) as error:
                    print('RESET_FAILED', error, flush=True)
            GLib.timeout_add(500, acknowledge, channel)

        def scanout(channel, prop):
            counts['scanouts'] += 1

        def input_ready(channel, event):
            if event == Spice.ChannelEvent.OPENED:
                channel.key_press(30)
                channel.key_release(30)
                counts['inputs'] += 1

        def new_channel(current_session, channel):
            channels.append(channel)
            if isinstance(channel, Spice.DisplayChannel):
                GObject.Object.connect(channel, 'gl-draw', draw)
                GObject.Object.connect(channel, 'notify::gl-scanout', scanout)
            if isinstance(channel, Spice.InputsChannel):
                GObject.Object.connect(channel, 'channel-event', input_ready)
            channel.connect()

        GObject.Object.connect(session, 'channel-new', new_channel)
        session.connect()

        def poll():
            if process.poll() is not None:
                loop.quit()
                return False
            return True

        def finish():
            loop.quit()
            return False

        GLib.timeout_add(100, poll)
        GLib.timeout_add_seconds(args.duration, finish)
        loop.run()
        alive = process.poll() is None
        if alive:
            # Leave modifier/key state held so server destruction must release
            # it through the input callbacks (the old implementation frees them).
            for channel in channels:
                if isinstance(channel, Spice.InputsChannel):
                    channel.key_press(29)
                    channel.key_press(30)
            context = GLib.MainContext.default()
            deadline = time.monotonic() + .3
            while time.monotonic() < deadline:
                context.iteration(False)
                time.sleep(.01)
            execute('quit')
            process.wait(timeout=10)
        print('SUMMARY', json.dumps(dict(counts, alive_before_quit=alive,
                                        exit=process.returncode)), flush=True)
        passed = alive and process.returncode == 0 and counts['inputs'] > 0
        if args.video == 'gl':
            passed = passed and counts['resets'] == args.resets and counts['acks'] > 0
        result = 0 if passed else 1
    finally:
        if session:
            session.disconnect()
        if process.poll() is None:
            process.kill()
            process.wait()
        if replies:
            replies.close()
        if qmp:
            qmp.close()
        logfile.close()
        print(logpath.read_text(), flush=True)
        if serialpath.exists():
            for line in serialpath.read_text(errors='replace').splitlines():
                if line.startswith(('EGL_', 'GL_', 'SHADER_', 'KMS_')):
                    print(line)
    raise SystemExit(result)
