# RDP soft keyboard input in Firefox

Validated on 2026-10-20. Weston `16.0.0-r6` fixes the previously empty
`xf_input_unicode_keyboard_event()` implementation. This addresses the reported
iOS Microsoft RDP screen keyboard failure in Firefox.

The backend emits a complete stroke on Unicode key-down, ignores key-up, decodes
UTF-16 surrogate pairs, and substitutes U+FFFD for malformed pairs. It uses the
current keyboard mapping, or synthesizes Shift where possible. Other characters
use a temporary one-level mapping on an unused key. The original map, lock
state, and layout group are restored. A bounded per-peer queue waits for held
keys before changing the shared seat's map; disconnect removes the timer and
queued text. Typed Unicode is not written to the backend debug log.

Firefox's existing `/usr/bin/firefox-esr` wrapper sets `GDK_BACKEND=wayland` and
`MOZ_ENABLE_WAYLAND=1`; no browser configuration change is needed.

## Validation

The affected package build passed:

```sh
make package/feeds/video/weston/compile -j8 V=s
```

All Weston patches applied to a fresh 16.0.0 source archive with `--fuzz=0`.
The resulting RDP sources matched the compiled sources. Checkpatch passed with
`--no-tree --no-signoff --ignore SPLIT_STRING`. `.config` was unchanged.

A disposable KVM guest booted the current native-systemd image, then installed
the exact signed `weston-16.0.0-r6.apk`. This was a package upgrade test; a new
complete image was not built. The guest used q35/OVMF, two vCPUs, 2 GiB RAM,
VirtIO VGA, and isolated user networking with loopback-only forwarded ports.

A FreeRDP 3.32.2 test client sent actual Unicode and scan-code RDP events.
Firefox ESR 153.5.0 opened a local test page through its normal Wayland wrapper.
Assertions read the textarea value directly through Marionette, rather than
relying on asynchronous HTTP input notifications, which can arrive out of order.

| Firefox check | Result |
| --- | --- |
| `abcABC123 !@中文😀`, with Unicode down/up events | Passed |
| Burst of 200 mixed Latin, CJK, punctuation, accented and supplementary characters | Passed |
| Unicode queued while Shift is held, then delivered after release | Passed |
| Backspace and newline | Passed |
| Malformed UTF-16 surrogate sequences | Passed |
| Ordinary scan-code letters and Shift | Passed |
| Exact Unicode text with Caps Lock enabled | Passed |
| Disconnect while Ctrl is held | Passed |
| New connection types without a stuck Ctrl modifier | Passed |

A native GTK Wayland entry also received mixed CJK/emoji input. A GTK Xwayland
entry received `abcABC123 !@` through existing mappings and synthesized Shift.
Arbitrary Unicode characters absent from the X11 keymap remain outside this
fix's acceptance scope: asynchronous X11 keymap queries can lose characters
from a temporary mapping. Use the ordinary Wayland Firefox wrapper for the
reported case. The physical iOS client still needs a user retest.

## Physical router deployment

Only the signed Weston package was installed, after target-side signature
verification and an offline simulated transaction. `/etc/init.d/desktop restart`
activated it without rebooting the router. The RDP listener returned on
`192.0.2.1:3389`; the running Weston loaded the new backend. The packaged,
QEMU-installed, and physically installed backend SHA256 matched:

`2edc468355aa0bacade9e95916ed7f48c793a3e095553d357b54621e7f717aaa`.

Boot ID, kernel/kmod package inventory, `/boot/vmlinuz`, desktop/network/firewall/
DHCP/Passwall configuration, RDP SAM, and TLS certificate/key hashes were
unchanged. The previous signed r5 package and desktop configuration backup are
root-only under `/root/rdp-unicode-backup-20261020` on the router.

No feed was published or firmware flashed. Source changes are committed locally
in the video feed; the replayable delta and commit provenance are
`patches/feeds/0011-video-rdp-unicode.patch` and
`configs/desktop-rdp-unicode-feeds.json`.

Test sources, nine assertion results, build and deployment logs, and hashes are
retained in
[`openwrt-rdp-unicode-validation-20261020`](/srv/openwrt-validation/openwrt-rdp-unicode-validation-20261020).
Disposable guest disks and test credentials are removed after validation.
