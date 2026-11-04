# Physical GNOME deployment, 2026-10-28

Published signed packages and deployed GNOME on `192.0.2.1` for the existing
ordinary account `builder` (UID 32769). Native GNOME Remote Desktop serves RDP
on LAN TCP 3389. Sunshine retains KMS capture, Intel H.264 VAAPI and its existing
Moonlight pairing state. The old launcher and seatd are removed;
there is no VNC listener on port 5900.

## Publication and installation

The coordinated publisher passed signed-index/package checks, router upgrade
simulation and the final ELF transition audit, with `same_version_rebuilds=[]`.
Rebuilt dependency recipes received releases beyond their published/reserved
identities. The version regression test now covers the affected recipes,
including FFmpeg's separate executable and library allocations.

The latest userspace snapshot is
`/srv/openwrt-feeds/public/snapshots/20261028T135510.684643Z`, for ABI
`7.3~5001c59b1072ebdf1a2ed551a854f37a-r1`. GNOME packages are also available
through its signed `custom` projection. The publisher updated the kernel
channel to generation 37; this deployment did not install that kernel.

The initial offline transaction installed 60 packages, upgraded 61 and replaced
`libudev-zero` with native libudev. Every incoming payload matched the pinned
published manifest and verified against the router's existing signing trust.
A repeated simulation matched the reviewed transaction before installation.
Two subsequent signed single-package updates installed `colord-1.4.8-r3` and
`openwrt-desktop-21`. All 121 reviewed final package versions match the installed
database.

Recorded GNOME Shell, RDP and Sunshine PIDs were preserved during deployment.
Temporary version pins introduced for installation were removed; the original
libc pin advanced from `2.43-r6` to `2.43-r7`, as required by the matching
character-conversion and UTF-8 locale payloads.

## Live migration fixes

- Native libudev provides the legacy `libudev-zero` virtual selection while
  excluding the actual old implementation. Both a signed isolated solver proof
  and simulation on the physical router verified the provider replacement.
- The colord account must be declared inside the package definition. Its new
  dynamic user/group declaration avoids the old proposed numeric ID 191,
  which this machine already uses for `libvirt-qemu`. The installed sysusers
  definition recovered the live account; the corrected package handles future
  installations.
- A persistent Mutter mode request opens a confirmation dialog and reverts
  without approval. Unattended startup now applies the legacy UCI resolution
  temporarily on each session until GNOME Settings saves its own `monitors.xml`.
  It waits for monitor state and preserves an existing GNOME layout. The
  previous `1920x1080@60` preference survives the tested desktop restart.
- The saved WirePlumber HDMI selection referred to its old sysfs-derived node
  name. It now selects the same HDMI device by its native-udev name,
  `alsa_output.pci-0000_00_1f.3.hdmi-stereo`. Ordinary playback then reaches both
  RDP and Sunshine capture; an explicit playback target is not required.

## Physical acceptance

| Check | Result |
| --- | --- |
| Ordinary local session | One GNOME Wayland seat0/VT7 session, UID 32769; unlocked keyring and LAN-only remote listeners |
| GPU renderer | `Mesa Intel(R) UHD Graphics (JSL)`, OpenGL ES 3.2, Mesa 26.2.2 |
| RDP input | Actual FreeRDP client keys committed text in the native GTK4 application, before and after desktop restart |
| Chinese input | Visible Pinyin candidates and `你好abc`, using the preserved Ctrl+Shift+Return shortcut |
| Clipboard | Unicode text, Chinese and arrows transferred both ways through RDP |
| RDP playback/microphone | Injected 1 kHz signals recorded at the opposite endpoint; nonzero RMS and frequency-power ratios well above 100 |
| Sunshine | Actual Moonlight protocol receiver, KMS capture and `h264_vaapi` using Intel iHD 26.3.5; the Jasper Lake HEVC/AV1 probe workaround remains enabled |
| Concurrent remotes | RDP remained established and received changing frames during the Moonlight stream |
| Desktop restart | Unattended GNOME/keyring/RDP startup, retained pairing, 1080p/60 mode, input, clipboard, both RDP audio directions and Moonlight capture/audio passed again |
| Pairing preservation | Both original clients and the complete original Sunshine Web/pairing state restored byte for byte after removing the temporary verification client |
| Runtime packaging | All 17 GI libraries and four schemas loaded successfully on the physical system |

The 60-second video measurement received and decoded 3,601 frames at 60.006 fps,
with zero frame-number gaps and all 55 injected F8 changes detected. Median
input-to-received-frame latency was 38.20 ms, p95 55.75 ms; p95 frame interval
was 19.35 ms. This excludes client decoding and display presentation. The test
surface changes its animation at 30 Hz, so distinct-frame rate is not a test
of 60 distinct game frames per second.

The initial audio measurement exposed the stale HDMI identifier described
above. After correction, ordinary default playback produced nonzero Moonlight
audio. The complete post-restart 20-second run decoded all 1,200 frames, with
zero frame-number gaps, 15/15 input changes and audio RMS 920.095. Its session
and stream PIDs stayed stable. Separate post-restart RDP measurements gave
playback RMS 114.00 and microphone RMS 1637.14, with strong 1 kHz discrimination.

During that short stream, sampled PSS was 112.41 MiB for Shell, 50.01 MiB for
Sunshine, 57.93 MiB for RDP and 67.55 MiB for Fcitx. RDP consumed approximately
one CPU core during the animated concurrent-client workload. These are bounded
samples, not a total desktop RAM requirement or a sustained gaming benchmark.

## Preservation and completion

- Running kernel remains generation 30,
  `7.3-owrt-5001c59b1072ebdf1a2ed551a854f37a-r1-g30`; boot ID is unchanged.
- WAN, WAN IPv6, LAN and WireGuard remain up; the PPPoE default route remains
  `10.36.80.1`. Kernel checks pass, and all 13 recorded protected router files
  retain their hashes.
- All 11 recorded existing TLS/RDP/IME files retain their bytes. The existing
  Fcitx configuration/profile and Sunshine pairings were preserved.
- Feed indexes refreshed successfully without changing installed packages or
  world. Only the two preexisting hostname-sync unit failures remain.
- The independent rollback timer is disarmed after acceptance. Signed rollback
  packages, the original world/database and private configuration archives remain
  under `/root/gnome-deploy-20261028T092143Z/`.
- The original host `.config` is restored byte for byte. No commit, push, firmware
  flash or physical-machine reboot was performed.

Private evidence is under `bin/deployment/gnome/20261028T092143Z/`, including
publication receipts, reviewed package plans, signatures, captures, metrics,
`final-health.json` and the deployment RDP credential file. This directory
contains credentials and is excluded from source publication.

Physical reboot acceptance, extended GPU/thermal/memory soak, headless changes,
and real Windows/macOS RDP/Moonlight GUI clients remain separate checks.
The earlier [VM report](gnome-desktop-validation.md) records broader application
IME and reconnect coverage; those VM results are not physical-client acceptance.

## Input-method follow-up

At 22:38 local time Fcitx exited successfully while the GNOME session remained
active. The original `Restart=on-failure` policy left it stopped, removing its
Kimpanel indicator. The initiating action was not established from the journal.
Signed `openwrt-desktop-ime-1-r4` now uses `Restart=always`, scoped to the GNOME
session, and is published and installed on the physical machine.

At the user's request, the existing profile's primary shortcut is Ctrl+Space;
its Ctrl+Shift+Return fallback remains intact. Package defaults and the personal
image template also use Ctrl+Space. Other profile settings and dictionaries
were not replaced. Through an actual RDP client, Ctrl+Space activated Pinyin,
displayed candidates, committed `你好abc` and switched back to English. A
requested clean Fcitx exit was followed by automatic recovery and a second
successful input test, with Kimpanel active and unchanged Shell/RDP PIDs.
Private follow-up evidence is under
`bin/deployment/gnome-ime/20261028T144219Z/`.
