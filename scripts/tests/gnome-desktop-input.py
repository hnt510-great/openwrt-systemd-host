#!/usr/bin/env python3
"""Native GTK input/clipboard fixture for disposable desktop acceptance.

Run as the desktop user. The private output directory contains state.json and
accepts command.json with {"copy": "text"} or {"read_clipboard": true}.
Keyboard input must arrive through the actual local or remote client.
"""
import argparse
import json
import os
from pathlib import Path

import gi

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--gtk', choices=['3', '4'], default='4')
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
os.umask(0o077)
args.out.mkdir(parents=True, exist_ok=True)
gi.require_version('Gtk', args.gtk + '.0')
gi.require_version('Gdk', args.gtk + '.0')
from gi.repository import Gdk, Gio, GLib, Gtk

state = {'pid': os.getpid(), 'gtk': args.gtk, 'text': '', 'keys': []}


def save():
    temporary = args.out / 'state.tmp'
    temporary.write_text(json.dumps(state, ensure_ascii=False) + '\n')
    temporary.replace(args.out / 'state.json')


def changed(buffer):
    state['text'] = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
    save()


def key(keyval):
    state['keys'].append(Gdk.keyval_name(keyval))
    state['keys'] = state['keys'][-100:]
    save()
    return False


def activate(app):
    window = Gtk.ApplicationWindow(application=app, title='GNOME acceptance GTK' + args.gtk)
    window.set_default_size(700, 420)
    text = Gtk.TextView()
    text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    text.get_buffer().connect('changed', changed)
    if args.gtk == '4':
        window.set_child(text)
        controller = Gtk.EventControllerKey()
        controller.connect('key-pressed', lambda _c, val, _code, _mods: key(val))
        text.add_controller(controller)
        clipboard = Gdk.Display.get_default().get_clipboard()
    else:
        window.add(text)
        text.connect('key-press-event', lambda _w, event: key(event.keyval))
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        window.show_all()

    def clipboard_done(source, result):
        try:
            state['clipboard'] = source.read_text_finish(result)
        except GLib.Error as error:
            state['clipboard_error'] = str(error)
        save()

    def poll():
        path = args.out / 'command.json'
        if path.exists():
            command = json.loads(path.read_text())
            path.unlink()
            if 'copy' in command:
                if args.gtk == '4':
                    clipboard.set(command['copy'])
                else:
                    clipboard.set_text(command['copy'], -1)
            if command.get('read_clipboard'):
                if args.gtk == '4':
                    clipboard.read_text_async(None, clipboard_done)
                else:
                    state['clipboard'] = clipboard.wait_for_text()
                    save()
        return True

    GLib.timeout_add(100, poll)
    window.present()
    text.grab_focus()
    save()


app = Gtk.Application(application_id='org.openwrt.DesktopAcceptance.Gtk' + args.gtk,
                      flags=Gio.ApplicationFlags.NON_UNIQUE)
app.connect('activate', activate)
app.run([])
