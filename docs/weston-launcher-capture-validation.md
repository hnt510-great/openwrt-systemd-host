# Weston launcher and optional Sunshine capture validation

Validated on 2026-10-26. The launcher and capture packages were built, installed
in a disposable QEMU guest, then installed on the physical N5105. KMS remains
the default. The Weston capture route is experimental and still requires
`force_composition=1` on the tested hardware.

## Implementation

- `openwrt-desktop-launcher` adds a panel Applications icon and a single-instance
  GTK3 search window. GIO supplies desktop-entry visibility, user overrides,
  localized names, generic names, keywords, icons and argument-safe launching.
  Search supports arrows, Enter and Escape and retains the desktop input method.
  Inherited panel listener descriptors and `WAYLAND_SOCKET` are discarded.
- GIO now packages its required `gio-launch-desktop` helper. The session includes
  system and user Flatpak export directories.
- `CONFIG_WESTON_PIPEWIRE` builds the optional backend; a Weston patch initializes
  mirror dimensions and refresh from the physical output before negotiating the
  stream. The PipeWire library package includes the video conversion SPA plugin.
- `desktop.main.sunshine_capture=weston` starts the user PipeWire daemon before
  Weston and mirrors the physical output to `weston.pipewire`. Sunshine resolves
  its object serial afresh and uses the common PipeWire capture implementation.
  DMA-BUF is used on Intel; system-memory buffers support software-rendered VMs.
  Missing producers fail explicitly without selecting KMS.
- Existing LAN restrictions, pairing state and the exact Jasper Lake H.264-only
  quirk remain in effect. The procd recovery path retains its existing backends.

Feed changes are exported in `patches/feeds/0025-packages-gio-desktop-launcher.patch`
and `0026-video-pipewire-capture.patch`, with bases and hashes in
`configs/weston-launcher-capture-feeds.json`. These are independent of unrelated
feed edits. No commits, pushes or feed publication were performed.

## Source and package checks

The launcher (3), capture/session (2), desktop audio (4), RDP configuration (3),
IME (2), and custom-package updater (39) tests passed. Strict Kconfig recursion
validation and `git diff --check` passed in the main and affected feed trees.
The existing configuration gained only the launcher and Weston PipeWire selects;
previous selections were retained. Focused builds passed for the seven packages
below. Kernel checkpatch was also run on the GTK source; it reports declaration
and SPDX style diagnostics, including its multi-pointer declaration rule.

| Package | Installed version |
| --- | --- |
| glib2-gio | 2.88.1-r5 |
| libpipewire | 1.6.10-r4 |
| weston | 16.0.0-r13 |
| openwrt-desktop | 17 |
| openwrt-desktop-audio | 1-r2 |
| openwrt-desktop-launcher | 1-r1 |
| sunshine | 2026.914.233613-r5 |

The source test commands are:

```sh
python3 scripts/tests/test-desktop-launcher.py
python3 scripts/tests/test-sunshine-weston.py
python3 scripts/tests/test-desktop-audio.py
python3 scripts/tests/desktop-rdp-config.py
python3 scripts/tests/test-desktop-ime.py
python3 scripts/tests/test-custom-package-updates.py
```

## Guest checks

The disposable QEMU guest used 2 vCPUs, software rendering and software H.264.
The launcher displayed and filtered applications; Enter launched Weston Terminal.
A separate isolated target-userspace RDP IME check on the host entered
`你好abc` correctly. An authenticated real
FreeRDP client and a TLS VeNCrypt VNC client displayed the desktop with the
PipeWire mirror enabled. FreeRDP must advertise its clipboard channel for the
existing Weston RDP activation code; the probe used an isolated Xvfb display.

A 20-second Weston capture decoded all 566 received frames at 1280x800 with
nonzero Opus audio. Software VM timing is not a hardware performance result.
Stopping PipeWire left Weston and its RDP/VNC listeners running; restarting the
desktop after restoring audio services recreated the mirror. The backend does
not automatically recreate its producer after the PipeWire daemon disappears.

## Physical comparison

The machine has Intel Jasper Lake `8086:4e61`, i915/iHD, and a 1920x1080@60 output.
Both final-package trials used H.264 VAAPI, the same isolated Firefox profile,
animated canvas/video fixture and 40-second authenticated headless Moonlight
receiver. Production pairing state was never used for the probe. Logs confirm
1920x1080 DMA-BUF capture on the Weston route.

| Measurement | KMS | Weston PipeWire |
| --- | ---: | ---: |
| Received / decoded frames | 2395 / 2395 | 2344 / 2344 |
| Received fps | 60.02 | 58.82 |
| Distinct frame fps | 58.84 | 58.82 |
| Frame gap p95, ms | 17.65 | 19.16 |
| Detected input changes | 35 / 35 | 35 / 35 |
| Input to received frame median, ms | 48.72 | 47.68 |
| Input to received frame p95, ms | 63.91 | 53.32 |
| Host processing p95, ms | 8.0 | 8.5 |
| Weston CPU, percent of one core | 22.67 | 20.10 |
| Probe Sunshine CPU, percent of one core | 14.58 | 15.00 |
| PipeWire CPU, percent of one core | 2.18 | 2.03 |
| Decoded Opus peak / RMS | 1719 / 1107.73 | 1691 / 1104.04 |

Latency ends at receipt of the encoded frame and excludes client decode/display.
CPU uses process tick deltas over each run; this is one short comparison, without
statistical confidence intervals. It does not establish a performance advantage.

A separate 12-second `force_composition=0` trial produced stale Firefox/mirror
frames (0 of 7 input changes detected), despite active audio. Therefore this
route does **not** yet solve direct-scanout capture on this hardware. Keep forced
composition enabled. The physical launcher window was also captured successfully
after restoring KMS. Some applications lack theme icons and show GTK's fallback.

## Deployment and restored state

All seven signed payloads were hash-checked, signature-verified and simulated
offline before the exact local transaction. Only six upgrades and the launcher
installation were applied. A root-only backup, six signed rollback APKs and an
independent rollback timer protected the deployment. The timer was canceled
after verification; the root backup remains available.

Final physical settings are `sunshine_capture=kms`, `force_composition=1`.
Weston, Sunshine, PipeWire and WirePlumber are active, Weston has zero restarts,
and LAN RDP/VNC listeners remain available. Production Sunshine again reports
KMS and H.264 VAAPI. Original credentials, TLS keys, RDP SAM, Sunshine pairing
state, network/firewall/DHCP/Passwall configuration and kernel/boot ID were
compared with the backup and are unchanged. APK world retains its original
entries plus the launcher. No physical reboot or kernel installation occurred.

Sanitized screenshots, package hashes, stream metrics and selected capture logs
are in `bin/validation/weston-launcher-capture/` (generated, not source files).
Probe source lives in `scripts/tests/sunshine-stream-{client.c,probe.py,metrics.py}`
and `desktop-capture-snapshot.py`. Test credentials and session manifests are
private temporary data and must not be published.

User-visible macOS Moonlight acceptance, extended reconnect/soak testing,
physical reboot persistence and a complete fullscreen/window-transition matrix
remain unverified. No global application hotkey or panel dropdown was added.
