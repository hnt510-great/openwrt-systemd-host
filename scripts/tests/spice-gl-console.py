#!/usr/bin/python3
"""Check real SPICE GL painting, input and passive reconnects on a local socket.

Run on a desktop with GTK3 and SPICE GI. The guest must show a static menu
where Down/Up only change selection. This never presses Enter or installs.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path

import gi

for name, version in [('Gtk', '3.0'), ('Gdk', '3.0'), ('GdkPixbuf', '2.0'),
                      ('SpiceClientGLib', '2.0'), ('SpiceClientGtk', '3.0')]:
    gi.require_version(name, version)
from gi.repository import Gdk, GdkPixbuf, GLib, GObject, Gtk
from gi.repository import SpiceClientGLib as Spice, SpiceClientGtk

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--socket', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--reconnects', type=int, default=2)
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=True)
epoxy = ctypes.CDLL('libepoxy.so.0')
read_pixels = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
                              ctypes.c_void_p).in_dll(epoxy, 'epoxy_glReadPixels')
state = {'session': None, 'window': None, 'display': None, 'channels': [],
         'scanouts': 0, 'draws': 0, 'cycle': 0, 'exit': 1, 'captures': {}}


def gl_areas(widget):
    if isinstance(widget, Gtk.GLArea) and widget.get_mapped():
        yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from gl_areas(child)


def capture(label):
    display = state['display']
    if display is None or not display.get_property('ready'):
        raise RuntimeError('SPICE display is not ready: ' + label)
    areas = list(gl_areas(display))
    if areas:
        area = areas[0]
        area.make_current()
        area.attach_buffers()
        width = area.get_allocated_width() * area.get_scale_factor()
        height = area.get_allocated_height() * area.get_scale_factor()
        data = ctypes.create_string_buffer(width * height * 4)
        read_pixels(0, 0, width, height, 0x1908, 0x1401, data)
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(data.raw),
                    GdkPixbuf.Colorspace.RGB, True, 8, width, height, width * 4).flip(False)
    else:
        window = display.get_window()
        pixbuf = Gdk.pixbuf_get_from_window(window, 0, 0, window.get_width(), window.get_height())
    data = pixbuf.get_pixels()
    channels = pixbuf.get_n_channels()
    colors = {data[i:i + channels] for i in range(0, len(data) - channels, channels * 17)}
    if len(colors) < 4:
        raise RuntimeError('Blank or unpainted GL display: ' + label)
    pixbuf.savev(str(args.out / (label + '.png')), 'png', [], [])
    digest = hashlib.sha256(data).hexdigest()
    state['captures'][label] = {'sha256': digest, 'sampled_colors': len(colors)}
    return digest


def send_key(scancode):
    channel = next(c for c in state['channels'] if isinstance(c, Spice.InputsChannel))
    channel.key_press(scancode)
    channel.key_release(scancode)


def channel_new(session, channel):
    state['channels'].append(channel)
    if isinstance(channel, Spice.DisplayChannel):
        window = Gtk.Window(title='Installer SPICE GL validation')
        window.set_decorated(False)
        display = SpiceClientGtk.Display.new(session, channel.get_property('channel-id'))
        window.add(display)
        window.set_default_size(1024, 768)
        window.show_all()
        state.update(window=window, display=display)
        GObject.Object.connect(channel, 'notify::gl-scanout', count_scanout)
        GObject.Object.connect(channel, 'gl-draw', count_draw)
    channel.connect()


def count_scanout(*unused):
    state['scanouts'] += 1


def count_draw(*unused):
    state['draws'] += 1


def connect():
    session = Spice.Session()
    session.set_property('unix-path', str(args.socket))
    session.set_property('gl-scanout', True)
    state['session'] = session
    GObject.Object.connect(session, 'channel-new', channel_new)
    session.connect()


def disconnect():
    state['session'].disconnect()
    if state['window']:
        state['window'].destroy()
    state.update(channels=[], window=None, display=None)


def step(phase):
    try:
        if phase == 'initial':
            capture('initial')
            send_key(0x150)  # XT extended Down
            GLib.timeout_add_seconds(1, step, 'down')
        elif phase == 'down':
            changed = capture('down')
            if changed == state['captures']['initial']['sha256']:
                raise RuntimeError('SPICE Down key did not change the menu')
            send_key(0x148)  # XT extended Up
            GLib.timeout_add_seconds(1, step, 'up')
        else:
            capture('up' if phase == 'up' else 'reconnect-' + str(state['cycle']))
            if state['cycle'] < args.reconnects:
                disconnect()
                state['cycle'] += 1
                connect()
                # No key, resize or forced redraw is sent on these connections.
                GLib.timeout_add_seconds(3, step, 'reconnect')
            else:
                if state['scanouts'] < args.reconnects + 1:
                    raise RuntimeError('Not every connection received a GL scanout')
                state['exit'] = 0
                Gtk.main_quit()
    except Exception as error:
        state['error'] = str(error)
        Gtk.main_quit()
    return False


def timeout():
    state['error'] = 'SPICE check timed out'
    Gtk.main_quit()
    return False


try:
    connect()
    GLib.timeout_add_seconds(4, step, 'initial')
    GLib.timeout_add_seconds(45, timeout)
    Gtk.main()
finally:
    disconnect()
    result = {k: v for k, v in state.items() if k not in ('session', 'window', 'display', 'channels')}
    (args.out / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
raise SystemExit(state['exit'])
