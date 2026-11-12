# GNOME desktop audio validation

## GNOME RDP Opus preference and Remmina gaps, 2026-11-12

Remmina 1.4.43 with FreeRDP 3.33.0 on a Fedora 45 client had periodic music
gaps. Each gap was exactly as long as the client's `latency:` buffer.
`gnome-remote-desktop` 51.0-r7 adds patch 006, which prefers Opus (48 kHz,
20 ms packets) over AAC (44.1 kHz, 1024-frame packets).

| Check | Result |
| --- | --- |
| r6 baseline, AAC 44.1 kHz, `latency:60` | 59.4 ms gaps 6.49 s apart (`rdp_stream.wav`); the same gaps were present at the Bluetooth sink (`bt_sink.wav`) |
| r6 baseline, AAC 44.1 kHz, `latency:200` | 199.4 ms gaps about 21.3 s apart (`rdp_stream2.wav`, `rdp_stream3.wav`). With either buffer, this is a 0.93 % shortfall |
| Server capture rate | A probe set up like GRD's capture stream (S16, 44.1 kHz, forced quantum 256, keep-last-buffer) received 44100.0 frames/s from the 48 kHz HDA sink over 8 s; 0 cycles had more than one buffer |
| Server AAC encoder | fdk-aac with GRD's parameters consumed 4096000 of 4096000 samples in 2000 calls and produced one AU per 1024 frames |
| Client cause | FreeRDP 3.33.0 `rdpsnd_pulse_play` adds `pa_bytes_to_usec(size)/1000` (whole milliseconds) to `play_end`, so each 23.22 ms AAC packet counts as 23 ms, 0.94 % short. When the estimate passes the clock, the client inserts `latency` ms of silence. FreeRDP 3.33.1 checks the real queue (`rdpsnd_pulse_ran_dry`); Fedora offered only 3.33.0 |
| Client workaround, r6, `rate:48000` (Opus only) | 0 gaps in 43.0 s (`rdp_48k.wav`) |
| Package build | `make package/custom/gnome-remote-desktop/{clean,compile}` passed; `test-gnome-rdp-audio-latency.py` passed |
| Router installation | Local signed r7 APK (SHA256 below) installed, and only the user `gnome-remote-desktop.service` restarted. The world checksum pin was replaced by the original unversioned entry. `apk fix` and `apk upgrade` simulations made no changes |
| r7, client offers AAC, Opus and PCM, `latency:60` | Remmina playback stream was 48 kHz; a continuous 440 Hz tone had 0 gaps in 43.0 s (`rdp_opus_fix.wav`, peak 8110, RMS 5668); 6 to 7 gaps would be expected before the fix |

Package SHA256:
`1c0fbed58c0d182bd35c9ed406ca1dd300c8a43d5f197f9bc3fb6e60543b01c4`.

r7 was installed from a local file and has **not** been published to the LAN
feed, which still holds r6. Clients that offer only AAC or PCM still get
44.1 kHz and are unaffected by this change. No Windows client was tested; the
existing `pw_stream_set_active called from wrong context` warning still
appears. The Remmina profile was returned to `sys:pulse,latency:60` without
`rate:48000`. A copy of the earlier `rate:48000` profile is on the client.

Evidence: `/srv/openwrt-validation/rdp-audio-validation-20261112/`: recordings,
`gaps.py` and its output `gaps.txt`, `SHA256SUMS`, router journal, and the
`pwprobe.c` and `aacprobe.c` sources.

## GNOME RDP latency policy and physical deployment, 2026-11-04

`gnome-remote-desktop` 51.0-r6 retains patch 005's recent render-latency
baseline, but removes the oldest-unacknowledged-block flush condition. A
constant output-device delay must not cause flushing; growing reported delay
still does. The removed condition could suppress all newly captured audio
from about 310 ms to 1990 ms after one missing confirmation, even while later
blocks were acknowledged normally.

| Check | Result |
| --- | --- |
| Patched C policy compiled from the release archive and zero-fuzz package patches | Passed all 11 scenarios: constant 520 ms, constant 3000 ms, low latency, jitter, missing/delayed/no confirmations, growing delay, device switch, stream reset and idle resume |
| Regression control with the original r5 patch | Missing-ACK and delayed-ACK scenarios fail; the corrected policy passes both |
| Related host suites | `test-desktop-audio.py` (3), `test-gnome-rdp-listener.py` (1), `test-apk-source-versions.py` (2), `desktop-rdp-config.py` (4): all passed |
| Targeted package build | `make package/custom/gnome-remote-desktop/compile -j6 V=s` passed |
| Signed APK | Local verification and verification using the router's existing trusted keys passed |
| Publication dry run and production publication | Router upgrade preflight passed; r6 was the only changed package; `same_version_rebuilds=[]`; kernel channel unchanged |
| Exact offline installation simulation | One upgrade, `gnome-remote-desktop` r5 to r6; the identical signed APK was installed |
| Router runtime | Only the user `gnome-remote-desktop.service` restarted; its executable SHA256 matches the extracted signed r6 payload |
| Real router-to-RDP-client playback | A continuous 20 s, 1 kHz tone was received for 20.1 s; every 100 ms window in the steady middle contained signal; RMS 1569.9, peak 2587, 1 kHz discrimination ratio 9.05e9 |
| Disconnect and reconnect | A second independent RDP connection received another 20 s tone for 20.1 s, with all steady middle windows containing signal and a 1 kHz discrimination ratio of 1.11e10; no server restart between connections |
| Client isolation | Separate PipeWire/PulseAudio graph and Xvfb; fixture self-test passed with zero physical devices; TLS fingerprint pinned from the router certificate |
| Published feed access | Router downloaded the r6 APK from `current/base`; SHA256 matched the installed artifact |
| Preservation | `.config`, router APK world and protected kernel file unchanged byte for byte; boot ID unchanged; `kernelctl check` passed, system running, no failed units; default route, DNS and fw4 table present |

Package SHA256:
`dc2e8cc058f7835ed1dacf7e24d8418b75e6eaa60a88296dc2c7e44155d88d99`.
Published snapshot:
`/srv/openwrt-feeds/public/snapshots/20261104T082509.076445Z`.

The client requested 500 ms playback latency. This is an actual RDP signal
test, not a measurement that the client's acknowledgments reported exactly
520 ms. The deterministic C scenarios cover that exact constant value and
missing confirmations. No physical speaker, Windows/macOS client, microphone,
full image, VM boot or router reboot was tested in this change. The existing
50 ms local-frame age limit remains unchanged. A device-latency step can
temporarily trigger drops until the two-bucket baseline adapts, within 10 s.

The kernel-style checkpatch tool reports GNOME's existing brace, typedef and
space-indentation conventions; the full GNOME package compiled successfully.
Both tracked changes and the new patch passed Git whitespace checks. A
PipeWire wrong-context warning appeared on client disconnect; the RDP daemon
remained active. Existing desktop settings and credentials were not changed.
The local-file APK transaction temporarily checksum-pinned the package in
world; its original unversioned entry was restored and the original complete
world hash verified. Rollback protection was disarmed after acceptance.

Evidence in the original private RDP audio validation archive:
original regression log, build log, publication receipts, signed old/new APKs,
installation simulation, executable hash comparison, private-client logs and
received PCM, `live-rdp-audio.json`, and router health/protection checks.

## Earlier desktop audio validation

Validation uses a disposable Q35/KVM native-systemd guest with emulated HDA,
USB audio hotplug, a private Weston desktop user, and isolated Linux client
audio servers. It does not use the physical router or the host sound devices.

- [VM validation](gnome-desktop-validation.md) covers measured RDP playback and
  microphone paths, PipeWire/Moonlight capture and persistence checks.
- [Physical deployment](gnome-desktop-deployment-20261028.md) records the actual
  output-device repair, Moonlight playback and RDP measurements after restart.

See [desktop audio](desktop-audio.md) for setup. Client negotiation, capture
backend and hardware results apply only to the configurations in those reports.
No additional audio validation was performed by this documentation update.
