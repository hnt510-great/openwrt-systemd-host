#!/usr/bin/env python3
"""Animated GTK4 surface for disposable GNOME streaming measurements.

F8 toggles a black/white indicator covering the left half. The right half
animates continuously. Use sunshine-stream-metrics.py with receiver logs;
its latency endpoint is receipt of the encoded frame, not client display.
"""
import argparse
import json
import os
from pathlib import Path
import time

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Graphene', '1.0')
from gi.repository import Gdk, Graphene, Gtk

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
os.umask(0o077)
args.out.mkdir(parents=True, exist_ok=True)
state = {'pid': os.getpid(), 'frames': 0, 'input_on': False, 'inputs': []}


def save():
    path = args.out / 'state.tmp'
    path.write_text(json.dumps(state) + '\n')
    path.replace(args.out / 'state.json')


class Surface(Gtk.Widget):
    def __init__(self):
        super().__init__()
        self.set_focusable(True)
        self.last_save = 0
        self.add_tick_callback(self.tick)
        controller = Gtk.EventControllerKey()
        controller.connect('key-pressed', self.key)
        self.add_controller(controller)

    def key(self, _controller, value, _code, _modifiers):
        if value != Gdk.KEY_F8:
            return False
        state['input_on'] = not state['input_on']
        state['inputs'].append(time.monotonic())
        save()
        self.queue_draw()
        return True

    def tick(self, _widget, _clock):
        self.queue_draw()
        now = time.monotonic()
        if now - self.last_save >= 5:
            save()
            self.last_save = now
        return True

    def do_snapshot(self, snapshot):
        width, height = self.get_width(), self.get_height()

        def fill(x, y, w, h, red, green, blue):
            rectangle = Graphene.Rect()
            rectangle.init(x, y, w, h)
            color = Gdk.RGBA()
            color.red, color.green, color.blue, color.alpha = red, green, blue, 1
            snapshot.append_color(color, rectangle)

        indicator = float(state['input_on'])
        fill(0, 0, width / 2, height, indicator, indicator, indicator)
        palette = [(1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (0, 1, 1), (1, 0, 1)]
        offset = int(time.monotonic() * 30) % len(palette)
        for index in range(6):
            fill(width / 2, index * height / 6, width / 2, height / 6,
                 *palette[(index + offset) % len(palette)])
        state['frames'] += 1


def activate(app):
    window = Gtk.ApplicationWindow(application=app, title='GNOME streaming acceptance')
    window.set_default_size(1280, 800)
    surface = Surface()
    window.set_child(surface)
    window.fullscreen()
    window.present()
    surface.grab_focus()
    save()


app = Gtk.Application(application_id='org.openwrt.StreamAcceptance')
app.connect('activate', activate)
app.run([])
