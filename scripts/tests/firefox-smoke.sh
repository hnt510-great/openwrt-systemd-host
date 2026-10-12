#!/bin/sh
# Read-only target checks. GUI, profiles and upgrades are tested in an isolated VM.
set -eu

test -x /usr/bin/firefox-esr
test "$(readlink /usr/bin/firefox)" = firefox-esr
/usr/lib/firefox-esr/firefox --version
test -f /usr/share/applications/firefox-esr.desktop
test -f /usr/share/icons/hicolor/48x48/apps/firefox-esr.png
test -f /usr/share/fonts/noto-cjk/NotoSansCJKsc-Regular.otf
fc-match ':lang=zh-cn' | grep -q NotoSansCJK
python3 - <<'PY'
import ctypes
import json

gdk = ctypes.CDLL('libgdk-3.so.0')
for name in ['gdk_x11_display_get_xdisplay', 'gdk_wayland_display_get_wl_display']:
    getattr(gdk, name)
for name in ['libX11.so.6', 'libX11-xcb.so.1', 'libxcb-shm.so.0', 'libasound.so.2', 'libavcodec.so.63']:
    ctypes.CDLL(name)
codec = ctypes.CDLL('libavcodec.so.63')
codec.avcodec_find_decoder_by_name.argtypes = [ctypes.c_char_p]
codec.avcodec_find_decoder_by_name.restype = ctypes.c_void_p
for name in [b'h264', b'aac']:
    assert codec.avcodec_find_decoder_by_name(name), f'Missing decoder: {name!r}'
with open('/usr/lib/firefox-esr/distribution/policies.json') as stream:
    assert json.load(stream)['policies']['DisableAppUpdate'] is True
print('GTK backends, media libraries and update policy passed')
PY
if [ "$(id -u)" = 0 ]; then
	if firefox-esr --version >/dev/null 2>&1; then
		echo 'Root browser launch was unexpectedly accepted' >&2
		exit 1
	fi
fi
printf 'Firefox runtime smoke checks passed\n'
