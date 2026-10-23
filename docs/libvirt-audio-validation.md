# Libvirt and QEMU audio validation

Validated on 2026-10-23 for x86_64/glibc native-systemd OpenWrt.

## Source and build checks

- `python3 scripts/tests/test-libvirt-audio.py`: five tests pass, covering real
  Unix socket ACL grant/revoke, idempotence, socket replacement, absent paths,
  invalid/root UIDs, symlink handling, and libvirt schema validation for all
  three graphics examples.
- `python3 scripts/tests/test-desktop-audio.py`: four existing checks pass.
- Strict `scripts/config/conf --fatalrecursive` normalization passes with
  `QEMU_AUDIO_PIPEWIRE` enabled and disabled. As in the earlier QEMU Kconfig
  checks, a temporary package Kconfig excludes the unrelated WeeChat/LuCI
  provider cycle. The option remains outside the QEMU package guard and has
  the same x86_64/glibc/systemd prerequisites as `libpipewire`.
- QEMU, libvirt, SPICE GTK and virt-manager package builds pass with a temporary
  normalized output configuration and `CONFIG_QEMU_AUDIO_PIPEWIRE=y` passed
  to make. The original `.config` is byte-for-byte unchanged.
- `git diff --check` passes for the main tree and packages feed. Reverse
  application checking passes for `0022-packages-qemu-pipewire.patch`.

Built versions are QEMU `11.1.1-r4`, libvirt/virsh `12.8.0-r5`, SPICE GTK
`0.41-r3`, and virt-manager/common/virt-install `5.1.0-r3`. The packages feed
base and patch are recorded in `configs/libvirt-audio-feeds.json`. Builds
report PipeWire `1.6.10` enabled, with SPICE retained. No feed commits were
created. Authorized publication and physical installation are recorded below.

## Disposable VM checks

A fresh qcow2 overlay over the existing combined UEFI image hosts the test.
It uses synthetic HDA devices and no host sound devices. The rebuilt APKs
are installed only in this guest, after exact offline transaction simulation
with `--no-network --repositories-file /dev/null`.

The outer guest runs native systemd. A dedicated desktop account owns its
PipeWire server. A nested libvirt guest produces/records audio through an
ICH9 HDA device; its QEMU process runs as `libvirt-qemu`. The nested audio
producer boots the baseline image's procd path, and tests use explicit ALSA
hardware devices, independently of a nested desktop audio service.

| Check | Result |
| --- | --- |
| Installed QEMU audio backends | `none`, `pipewire`, `spice`, `wav` |
| Systemd unit verification | Pass inside the guest |
| Unprivileged QEMU identity connects to selected user's PipeWire | Pass |
| Socket recreation | ACL restored automatically; connection succeeds |
| Revoke and reconnect | Connection rejected after revoke; restored after opt-in |
| Native-systemd reboot | Path unit active, ACLs restored and cross-user connection succeeds |
| Default virt-install SPICE XML | Sound card present without `--sound` |
| Native PipeWire guest playback | Monitor peak 13263, RMS about 7663 |
| Native PipeWire guest capture | Injected 660 Hz tone: peak 12091, RMS about 8456 |
| SPICE guest playback | Monitor peak 12000, RMS about 7583 |
| SPICE guest capture | Injected 660 Hz tone: peak 12000, RMS about 7655 |

Playback uses a 440 Hz signed 16-bit stereo tone at 48 kHz in the nested
system. The outer account records its default sink monitor. Capture injects
an outer null-sink monitor into the QEMU or SPICE client's recording stream;
the nested system records through its HDA capture device. Both paths require
nonzero measured samples. The SPICE client uses `SpiceClientGLib.Audio` with
the packaged GStreamer backend. Its session connects over guest loopback.

The ACL helper avoids repeated writes when ACLs already match. Boot creates
several runtime sockets in a burst, so the oneshot service disables its start
rate limit; the path unit retains its trigger limit. No unit instance is
enabled by package installation. All VMs sharing `libvirt-qemu` share the
selected audio server access once an administrator enables an instance.

Evidence, build logs, package SHA256 hashes, fixture scripts and disposable
VM disks are under `/tmp/openwrt-libvirt-audio-20261023/`.

## Acceptance boundary

These checks prove packaged backend support and synthetic bidirectional audio
through both native PipeWire and SPICE, including the cross-user access path.
No complete new firmware image was built. These signal tests use synthetic
devices; they do not prove physical microphone/speaker behavior, remote-client
behavior, latency or audiovisual sync. Existing VM definitions and the build
`.config` are unchanged. Physical package/backend checks follow.

## Authorized physical publication and installation

On 2026-10-23, the eight validated APKs were published in signed ABI snapshot
`20261023T145336.737174Z` and installed on `192.0.2.1`. Publication used an
isolated source projection with `--incremental --kernel-upgrade-view` for ABI
`6.18.55~628a4581533e057afecd1eb41702012b-r1`. The dry-run selected exactly
eight packages, with no reused filename containing different bytes. All
previously published APK hashes and the independent kernel channel remained
unchanged. Nine signed HTTP indexes and all eight APK downloads were verified.

The router verified signatures and hashes, simulated the exact offline
transaction, and installed the same eight files without network resolution.
The existing PipeWire `1.6.9-r4` and WirePlumber `0.5.18-r1` were retained;
the new QEMU runs successfully with those installed libraries. Libvirt's
active daemons were refreshed; the desktop and audio services were retained.
No system or user-session VMs were defined or running before installation.

The instance `libvirt-pipewire-access@32769.path` is enabled for the configured
desktop/audio account `desktop-user`. A temporary diskless, paused QEMU process
running as `libvirt-qemu` connected to this account's PipeWire and registered
both `Stream/Output/Audio` and `Stream/Input/Audio`. It was then terminated.
SPICE GStreamer elements and default virt-install sound-card generation pass.
No production VM definition was created or changed. This physical check proves
backend connectivity, not a guest's audible playback or microphone content.

The boot ID, kernel, UCI/libvirt configuration hashes, desktop PID, VM list and
original `/etc/apk/world` are unchanged. Direct-file installation temporarily
adds checksum constraints; only the eight transaction pins were removed by
restoring the exact original world file, preserving all pre-existing pins.
The router's LAN indexes were refreshed. No reboot or flash was performed.

Router backups, eight signed rollback APKs and a rollback script are retained
in `/root/libvirt-audio-deployment-20261023/`. The exact offline downgrade
transaction was simulated successfully. Local manifests, HTTP checks, hashes,
installation logs and protected-state audits are in
`/srv/openwrt-validation/openwrt-libvirt-audio-deploy-20261023-225132/`.
