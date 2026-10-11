#!/bin/sh
# Read-only runtime checks; account and GUI scenarios belong in an isolated VM.
set -eu
[ "$(cat /proc/1/comm)" = systemd ]
systemctl is-active --quiet virtqemud virtstoraged virtsecretd
virsh -c qemu:///system version
for app in virt-manager virt-install virt-manager-setup; do command -v "$app"; done
[ -x /usr/libexec/virt-manager-launch ]
[ -x /usr/bin/dbus-run-session ]
python3 - <<'PY'
import importlib
import gi
import cairo
import libvirt
import libxml2
for name, version in [
    ('GLib', '2.0'), ('GObject', '2.0'), ('Gio', '2.0'),
    ('GdkPixbuf', '2.0'), ('Pango', '1.0'), ('Atk', '1.0'),
    ('Gtk', '3.0'), ('GtkVnc', '2.0'), ('Vte', '2.91'),
    ('Libosinfo', '1.0'), ('LibvirtGObject', '1.0'),
    ('SpiceClientGLib', '2.0'), ('SpiceClientGtk', '3.0'),
]:
    gi.require_version(name, version)
    importlib.import_module('gi.repository.' + name)
    print(name, version, 'imported')
from gi.repository import Gio, Gtk
assert Gtk.get_major_version() == 3
assert Gio.SettingsSchemaSource.get_default().lookup('org.virt-manager.virt-manager', True)
print('virt-manager schema available')
connection = libvirt.open('qemu:///system')
assert connection.getLibVersion() >= 12008000
connection.close()
PY
for name in virtqemud virtstoraged virtsecretd; do
    stat -c '%a %U %G %n' "/run/libvirt/$name-sock"
    # Administration listeners may remain inactive on a fresh socket-activated boot.
    if [ -S "/run/libvirt/$name-admin-sock" ]; then
        [ "$(stat -c '%a:%U:%G' "/run/libvirt/$name-admin-sock")" = '600:root:root' ]
    fi
done
for name in virtlogd virtlockd; do
    [ "$(stat -c '%a:%U:%G' "/run/libvirt/$name-sock")" = '600:root:root' ]
done
# No management TCP listener is shipped; the only VNC LAN listener is Weston.
! awk '$4 == "0A" && $2 ~ /:(407D|4082)$/ { found=1 } END { exit !found }' /proc/net/tcp /proc/net/tcp6
virsh pool-list --all
virsh list --all
printf 'virt-manager runtime smoke checks passed\n'
