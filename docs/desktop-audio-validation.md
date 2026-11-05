# GNOME desktop audio validation

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
