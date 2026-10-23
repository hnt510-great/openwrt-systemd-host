#!/bin/sh
# Read-only target checks; --vaapi also requires usable hardware as this user.
set -eu
case "${1:-}" in
	'') hardware=0 ;;
	--vaapi) hardware=1 ;;
	*) echo 'Usage: firefox-smoke.sh [--vaapi]' >&2; exit 2 ;;
esac
[ "$#" -le 1 ] || { echo 'Usage: firefox-smoke.sh [--vaapi]' >&2; exit 2; }

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
for name in ['libva.so.2', 'libva-drm.so.2']:
    ctypes.CDLL(name)
util = ctypes.CDLL('libavutil.so.61')
util.av_hwdevice_find_type_by_name.argtypes = [ctypes.c_char_p]
util.av_hwdevice_find_type_by_name.restype = ctypes.c_int
vaapi = util.av_hwdevice_find_type_by_name(b'vaapi')
assert vaapi, 'FFmpeg has no VA-API device type'

class HWConfig(ctypes.Structure):
    _fields_ = [('pix_fmt', ctypes.c_int), ('methods', ctypes.c_int),
               ('device_type', ctypes.c_int)]

codec.avcodec_get_hw_config.argtypes = [ctypes.c_void_p, ctypes.c_int]
codec.avcodec_get_hw_config.restype = ctypes.POINTER(HWConfig)
for name in [b'h264', b'vp9']:
    decoder = codec.avcodec_find_decoder_by_name(name)
    assert decoder, f'Missing decoder: {name!r}'
    for index in range(64):
        config = codec.avcodec_get_hw_config(decoder, index)
        assert config, f'No VA-API configuration for {name!r}'
        if config.contents.device_type == vaapi:
            break
    else:
        raise AssertionError(f'No VA-API configuration for {name!r}')
with open('/usr/lib/firefox-esr/distribution/policies.json') as stream:
    assert json.load(stream)['policies']['DisableAppUpdate'] is True
print('GTK backends, FFmpeg VA-API codecs and update policy passed')
PY
if [ "$hardware" = 1 ]; then
	vainfo --display drm
fi
if [ "$(id -u)" = 0 ]; then
	if firefox-esr --version >/dev/null 2>&1; then
		echo 'Root browser launch was unexpectedly accepted' >&2
		exit 1
	fi
fi
printf 'Firefox runtime smoke checks passed\n'
