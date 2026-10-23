# Desktop audio validation

Validation uses a disposable Q35/KVM native-systemd guest with emulated HDA,
USB audio hotplug, a private Weston desktop user, and isolated Linux client
audio servers. It does not use the physical router or the host sound devices.

## Source checks

Run from the repository root:

```sh
python3 scripts/tests/test-desktop-audio.py
python3 scripts/tests/desktop-rdp-config.py
python3 scripts/tests/test-custom-package-updates.py
scripts/checkpatch.pl --no-tree --file feeds/video/frameworks/weston/files/rdpaudio.c
git diff --check
git -C feeds/packages diff --check
git -C feeds/video diff --check
```

The focused tests cover audio opt-in and desktop-user matching, the SSH PCM
stream contract, compositor lifecycle propagation, RDP configuration and the
custom package registry. Strict Kconfig recursion checking is also required.

`desktop-seat-retirement.c` exercises the compositor disconnect regression.
Compile it with the target compiler, staged `wayland-client` headers/library,
and the generated `tablet-unstable-v2-client-protocol.h` and protocol C file
from the Weston build. Run it as the desktop user with that session's
`XDG_RUNTIME_DIR` and `WAYLAND_DISPLAY`, while an RDP client is connected.
A tablet device must have initialized the tablet manager first; an active
Moonlight session supplies Sunshine's virtual pen tablet. After the probe's
ready message, disconnect RDP. The probe destroys an existing tablet
seat and requests another through the removed seat resource. It must print
`PASS`, and Weston must retain its PID without restarting. Use an outer timeout
to catch a missing RDP seat or disconnect.

For the VNC registry race, run the same probe with `--late-bind` before
connecting a VNC client. Connect and immediately disconnect VNC after its ready
message. The probe binds the removed seat global and requests inert pointer,
keyboard and touch resources. It must print `PASS`; the desktop shell and
compositor must remain alive across repeated connections.

Feed modifications are exported separately in
`configs/desktop-audio-feeds.json`. Verify they apply over the preserved local
feed baseline; do not replace unrelated feed changes.

## Guest signal checks

Generate one-second 997 Hz stereo fixtures at 48 kHz using FFmpeg in WAV, MP3,
ADTS AAC, Ogg Opus, Ogg Vorbis and FLAC. Copy them and the guest test to a
private VM directory. After `desktop-setup USER` and `desktop-audio-setup USER`,
run inside the guest as root:

```sh
python3 desktop-audio-guest.py --user USER --fixtures FIXTURES --output RESULTS --firefox
```

The test checks actual nonzero output monitor samples for native PipeWire,
ALSA, every codec and Firefox WebAudio. Firefox uses a disposable profile and
an automated click on a play button; autoplay policy is not bypassed. ALSA
recording must produce 48,000 frames. Emulated HDA has silent microphone input,
so that recording proves the capture path and format, not a physical microphone.

For remote validation, use a separate client PipeWire/Pulse server with null
sinks for received audio and an injected client microphone tone. Record the
received signal and assert peak > 100 and RMS > 20 in signed 16-bit samples.
Check RDP playback and microphone separately, including a reconnect and a
client-size renegotiation. Verify client microphone streams disappear after
disconnect and the compositor remains active. Verify the SSH companion as the
enrolled user; root and other users must be rejected.

Attach and remove a virtual USB audio device through QMP. Verify WirePlumber
discovers it without a restart, grants the selected-user ACL, removes the card
on unplug, and retains the original HDA card. Repeat after a guest reboot.

Sunshine acceptance additionally requires explicit KMS enrollment, Web UI
credential creation, Moonlight pairing and actual received Opus audio. Check
service startup, desktop-stop cleanup, capability and virtual-input permissions,
LAN binding and disabled UPnP. Package installation alone must not enroll a user.

## Acceptance boundary

Record package build, complete image build, cold-boot VM checks and client
signal results separately. Windows/macOS client acceptance and physical device
playback/capture require those clients and hardware. Publishing feeds and
installing on the physical router are separate operations.

## Results from the 2026-10-23 build

The 51 focused Python checks passed, strict Kconfig recursion checks passed,
and the RDP audio C file passed checkpatch with zero errors and warnings. All
previously selected configuration options were retained; 88 selections were
added. The complete `make -j3 V=s` build passed and all eight image SHA256
checks passed. The combined UEFI image SHA256 is
`8039501e53b4472a31da9c56bb8cdde53d9fa5b9f3a0615910b3887b25be404c`.

The final image was cold-booted in a fresh disposable guest. Running PipeWire,
WirePlumber, Sunshine and Weston payload hashes matched the image, and local
and remote signal checks were repeated. Reboot, recovery and sysupgrade
retention were also checked in a separate guest. The sysupgrade retention test
used the preceding image with Weston r8; enrollment and backup helpers are
unchanged in the final r9 image.

| Check | Result |
| --- | --- |
| HDA discovery, PipeWire and ALSA playback | Nonzero monitor signal |
| WAV, MP3, AAC, Opus, Vorbis and FLAC | Every fixture produced nonzero signal |
| ALSA capture | 48,000 frames at 48 kHz; emulated microphone is silent |
| Firefox WebAudio | Running at 48 kHz, nonzero monitor signal |
| SSH companion audio | Peak 2896, RMS about 1420; root rejected |
| RDP PCM playback and microphone | Both peaks 2896, RMS about 1211 / 1108 |
| RDP size renegotiation and disconnect | One microphone source; removed on disconnect; three tablet-seat retirement probes retained the compositor PID |
| VNC | TLS 1.3, X509Plain user authentication, 1280 by 800 desktop; five late-bind probes retained compositor and shell PIDs |
| USB audio add/remove | Detected without restarting WirePlumber; original HDA retained; repeated after reboot |
| Sunshine KMS and Moonlight | Software H.264 decoded; received Opus peak 3248, RMS about 1236 |
| Sunshine desktop lifecycle | Stops with the desktop; restarts through the desktop init script; pairing retained |
| Native-systemd reboot | Audio services, selected-user ACLs and Sunshine KMS capability restored |
| Procd recovery | VNC authenticated successfully; RDP audio disabled and audio/Sunshine daemons absent |
| Config-preserving sysupgrade | Desktop config, RDP identity, Sunshine enrollment, config and pairing hashes retained |

Concurrent Sunshine/RDP testing exposed invalid tablet-seat resources after
an RDP seat was removed. Weston patch 008 now detaches existing resources and
accepts late requests as inert resources. The dedicated protocol probe covers
both paths, including reconnects and client-size renegotiation. Patch 009 also
uses Weston's existing wl_output retirement grace period for seat globals, so
rapid VNC connections do not disconnect clients with in-flight registry binds.
The late-bind probe reproduced `global wl_seat is unavailable` before the fix.

RDP advertises interoperable PCM playback at 48/44.1 kHz and PCM microphone
input at 48 kHz. Application media decoding includes Opus; RDP Opus transport
is not enabled by this integration.

Moonlight UDP acceptance used a private user/network namespace and a hotplugged
virtual USB Ethernet link. QEMU user-network UDP forwarding timed out during
ENet setup, so it was not used as the audio acceptance path. The isolated
client audio server used no host sound devices. No feed publication or physical
router installation was performed during this VM validation phase. Windows/macOS clients, physical sound
devices, hardware VAAPI encoding, live SPICE sessions and Flatpak applications
were not exercised; their integration dependencies and usage are documented
separately from the tested Firefox/GStreamer paths.


## Signed publication and physical installation, 2026-10-23

Published 99 signed userspace APKs in snapshot `20261023T045717.059845Z`
for the router's existing ABI
`6.18.55~628a4581533e057afecd1eb41702012b-r1`. The kernel channel was
unchanged. All published payload hashes matched the downloaded files; the
router verified their signatures using its existing trusted keys. The exact
offline transaction was simulated before installing the same files: 14
upgrades and 85 additions, with no removals or downgrades. Installed package
identities matched all 99 published payloads. Repository indexes were refreshed,
and APK world constraints were normalized while preserving unrelated entries;
an offline fix simulation then required no package changes.

The existing user `desktop-user` was explicitly enrolled for desktop audio and
Sunshine KMS. PipeWire, WirePlumber and the PulseAudio compatibility service
are active. Selected-user sound/input ACLs, the restricted Sunshine executable
and KMS capability, and boot-time permission restoration are configured.
Sunshine is enabled for the next desktop session.

Physical-host digital tests used a temporary null sink, which was removed
when testing finished. PulseAudio and native PipeWire playback produced nonzero
monitor signals, as did WAV, MP3, AAC, Opus, Vorbis and FLAC decoding. The HDMI
sink was discovered. Physical speaker output and microphone capture were not
tested; the host exposed no hardware capture PCM.

No reboot or desktop restart was performed. The boot ID and existing Weston
PID remained unchanged, so the running desktop still uses the preceding
payloads. The read-only restart scan identified stale Weston and desktop portal
libraries. The user will reboot to activate the new desktop, RDP audio and
Sunshine lifecycle integration. Physical RDP/Moonlight client acceptance remains
pending that reboot; Sunshine Web UI credential creation and Moonlight pairing
also remain user actions at `https://192.0.2.1:47990`.

Protected network, firewall, DHCP, Passwall and SSH configuration hashes,
desktop TLS/authentication identities, the existing user's container identities
and states, and Flatpak application inventory were retained. Rollback APKs and
private configuration backups remain in the root-only directory
`/root/audio-deployment-20261023` on the router.

## Jasper Lake Sunshine GPU workaround, 2026-10-23

On the physical Intel `8086:4e61` host, Sunshine's startup HEVC VAAPI probe
with iHD 26.3.5 triggered two i915 `vcs0` command-stream resets and GPU hangs.
H.264 probing succeeded. Sunshine r2 now skips HEVC/AV1 probing and
advertisement on this PCI device when it is the sole render device. Other
GPU IDs and multi-GPU configurations are unchanged. This avoids the observed
failing encoding path; it does not repair or validate Intel HEVC encoding.

The focused Python suite passed, including five GPU-selection cases; shell
syntax and `git diff --check` passed. The Sunshine package build passed. The
exact tested launcher was checked inside the signed r2 APK. A narrow feed
publication examined only that APK and left the kernel channel unchanged.
HTTP payload hashes, existing-key signature verification and the offline
single-package upgrade simulation passed before physical installation.

Three consecutive patched Sunshine starts found the KMS monitor and passed
H.264 VAAPI encoder probing. None attempted HEVC/AV1 encoding or logged
capability failures; the kernel's GPU hang count stayed at the original two.
The earlier failed-capture process recovered after restarting Sunshine;
neither executable capabilities nor the systemd capability policy was changed.
The machine's boot ID and Weston PID remained unchanged. Desktop configuration,
APK world, Sunshine settings, certificates and pairing-state hashes were
preserved; only Sunshine runtime logs changed. Remote error-state and rollback
backups remain under `/root/sunshine-gpu-fix-20261023`.

This check covers the startup workload that reproduced the GPU hang. Extended
Moonlight streaming and a subsequent physical reboot were not tested here.
