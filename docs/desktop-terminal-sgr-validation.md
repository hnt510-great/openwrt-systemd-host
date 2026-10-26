# Weston terminal RGB SGR parsing

Validated on 2026-10-26 with Weston `16.0.0-r12`.

The reported `desktop-session[5162]: Unknown SGR code: 38` and color component
warnings came from `/usr/bin/weston-terminal`, as confirmed by the journal's
`_COMM`, `_EXE` and `_CMDLINE` fields. The terminal understood `38;5;n` and
`48;5;n`, but interpreted `38;2;r;g;b` components as separate attributes.
This produced warnings and could incorrectly enable bold, blink or underline.
The old indexed-color path also stopped processing later SGR attributes.

The video-feed patch consumes complete foreground/background color sequences,
validates component bounds, and continues with subsequent attributes. RGB
colors map to the nearest entry in the existing terminal palette; this does
not add full 24-bit color storage. Unsupported or truncated color payloads do
not become unrelated attributes. Other terminal protocols, such as OSC 8
hyperlinks and synchronized output, remain outside this change.

## Source and build checks

```sh
python3 scripts/tests/test-weston-terminal-sgr.py
make package/feeds/video/weston/compile -j3 V=s
git diff --check
git -C feeds/video diff --check
scripts/checkpatch.pl --no-tree --no-signoff --ignore BLOCK_COMMENT_STYLE \
  feeds/video/frameworks/weston/patches/010-terminal-consume-rgb-sgr-colors.patch
```

All Weston patches also applied to a fresh source archive with `--fuzz=0`;
the terminal source matched the compiled source.

The test applies the patch to the original source archive, compiles the actual
SGR implementation, and asserts RGB/indexed foreground/background handling,
subsequent attributes, resets, invalid bounds and truncated payloads.
The feed delta is saved in `patches/feeds/0024-video-terminal-sgr.patch`, with
its base recorded in `configs/desktop-terminal-sgr-feeds.json`.

## Physical router

The exact signed `weston-16.0.0-r12.apk` was verified on the router, with matching
local and remote SHA256:

`ed36e47268a49af09cf562227039dcf85e1bf4c91c119341cb38c4e842de51a5`.

An offline simulation selected only Weston r11 -> r12. The signed r11 APK was
retained and a timed rollback armed before installation, then cancelled after
successful checks. The local-file install added a checksum constraint to the
Weston world entry; the original world file was restored after checking that
this was its only difference.

A temporary terminal attached to the physical Wayland session printed the
reported RGB components and combined foreground/background sequences. The old
binary reproduced `Unknown SGR` warnings; the installed binary emitted none.
The terminal binary SHA256 is:

`68b36ace98f3fd3b50c0ae147167558dea1a9bd8f9c1b8768d781da63a4e0cf8`.

During installation, the existing desktop remained active with Weston PID
2422. Boot ID, desktop configuration and world file were unchanged, and
`kernelctl check` succeeded. The smoke terminal closed itself.

At the user's subsequent request, the desktop was restarted at 11:19 on
2026-10-26 (Asia/Singapore). Weston returned active with PID 32321 and GL
rendering; VNC (`192.0.2.1:5900`) and RDP (`192.0.2.1:3389`) were listening.
The boot ID was unchanged; no router reboot occurred. No disposable VM or
visual color-accuracy acceptance test was performed for this change.

The signed LAN feed publication changed only Weston in the video repository;
the kernel channel was unchanged. Its snapshot is
`/srv/openwrt-feeds/public/snapshots/20261026T031713.305391Z`.
The router downloaded the published APK through its configured LAN hostname,
verified its signature, and matched it byte-for-byte to the installed artifact.

Build, publication, deployment and before/after smoke logs are under
`build_dir/weston-sgr-fix-20261026/`.
