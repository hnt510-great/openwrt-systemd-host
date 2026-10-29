# GNOME desktop validation

Full GNOME firmware builds and disposable VM client checks have completed.
Existing Weston reports are historical evidence, not GNOME acceptance.
Physical-router deployment and hardware acceptance remain separate.
The subsequent [physical deployment report](gnome-desktop-deployment-20261028.md)
records signed publication, installation, hardware checks and Weston removal.

## Recorded run: 2026-10-28

Private artifacts are under
`bin/validation/gnome-desktop/20261027T024842Z/`. This directory includes
test credentials and must not be committed or published. The release image is
`gnome-svg-final.img.gz`, SHA-256
`ef37d14fd069c91f9818742931b6b41f4ee8a0f3de434beb79d54bcfa8ebf1cd`.
The normalized configuration is `gnome.config`, SHA-256
`f1396450a5a4e0c333bd3afa5a13058abc0c834ba8ed398086e157fbf3fb28b9`.
Source/feed heads and the original configuration are recorded in `baseline/`.

| Check | Observed result and evidence |
| --- | --- |
| Build and package checks | Complete firmware build; custom updater/version suites and desktop/RDP/IME/audio/keyring/listener checks pass. `final-check-*.log`, `gnome-svg-cache-image.log` |
| Session and rendering | Ordinary UID 2001, one seat0/VT7 Wayland session. Software rendering and VirGL exercised. VirGL reports the host RX 6600 XT through virtio; this is not Intel N5105 evidence. `vm-final/renderer.json`, guest prerequisite JSON |
| Shared application | Local QMP keyboard, native GNOME RDP and Moonlight input change the same application's text or marker without replacing Shell. `vm-software/ime-x11-local-first.json`, `ime-x11-exact.json`, stream captures |
| Clipboard and audio | Unicode clipboard both directions; known 1 kHz playback recorded at the RDP client and microphone signal recorded in the guest. Both have nonzero RMS and strong frequency discrimination. `vm-software/clipboard-r4.json`, `rdp-audio-first.json` |
| Chinese input | Candidates and `你好abc` commits in native GTK3, GTK4, Firefox, Xwayland and Shell search. Shell result returned through the RDP clipboard. `vm-software/ime-*.json`, `vm-release/shell-chinese.json` and candidate screenshots |
| Reconnect | Ten RDP and ten Moonlight reconnects with real application input and persistent session/application PIDs. `vm-software/rdp-reconnect.json`, `moonlight-reconnect.json` |
| Concurrent clients | RDP connection remains established and changing frames are received during the Moonlight soak. `vm-final/rdp-concurrent-check.json` |
| LAN lifecycle | Actual netifd LAN address change moves the listeners; removing the supplied LAN environment closes remotes while retaining the local desktop. Restoring LAN restores remotes. `vm-final/lan-migration.json` |
| Boot persistence | Three actual reboots in each rendering path preserve credentials, RDP input, Moonlight pairing and portal capture consent without local login. `vm-final/boot-persistence.json`, `vm-release/boot-persistence.json`. The fresh release software cycles take 69.48, 71.70 and 97.73 seconds including client checks. |
| Failure paths | Invalid RDP credentials produce `ERRCONNECT_LOGON_FAILURE`. Missing keyring bootstrap prevents desktop startup and leaves RDP closed; restoring the unchanged credential restores the session, RDP authentication and already-paired Moonlight capture/audio. Wrong-passphrase rejection is also tested against the real target keyring daemon on a private bus. `vm-release/invalid-rdp.json`, `keyring-negative.json`, `valid-rdp-after-keyring.json`, `after-keyring-stream.json`, keyring test log |
| Image contents | Required units, locale, typelib, schemas and icons present; retired Weston and GNOME system/headless/handover RDP paths absent; no preset desktop credentials. `final-image-payload-audit.json`. Fresh release first boot decodes an SVG application icon without a manual cache repair. |
| Router smoke | Disposable guest namespaces exercise LAN DHCP, native DNS, WAN DHCP and firewall/NAT; procd/netifd/SSH remain usable and fixture configuration is restored. `vm-software/router-smoke.log`. Kernel generation reports ready with no pending activation; installed package queries pass. `vm-final/package-kernel-smoke.log` |

The router fixture uses a temporary native DNS listener on port 1053 because
the preserved overlay redirects port 53 to Passwall. It does not prove the
physical WAN, upstream Internet DNS or the proxy DNS service. Kernel/package
checks are read-only lifecycle smoke checks, not an upgrade/rollback exercise.
Moonlight testing uses the actual protocol and `moonlight-common-c` receiver;
hardware-decoded Moonlight GUI clients still require separate acceptance.

The 30-minute VirGL stream used portal/PipeWire capture, H.264 with the
software `libx264` encoder, 1280×800 at 30 fps, an animated surface and a
periodic audio tone, with RDP connected.
All 54,000 received frames decoded, with zero frame-number gaps; distinct
frame rate was 29.999 fps. All 1,795 injected F8 changes appeared in the
encoded video. Median input-to-received-frame latency was 29.54 ms, p95
60.75 ms; p95 frame interval was 34.78 ms. This timing excludes client
decoding and display presentation. See `vm-final/soak-results.json`.

All six sampled session/stream process PIDs stayed unchanged over 60 samples.
After startup allocation, Sunshine PSS reached 169.96 MiB and ended there;
Shell PSS ended at 127.78 MiB and RDP at 67.58 MiB. These are individual
process measurements, not total desktop RAM requirements. See
`vm-final/soak-resource-summary.json` and `soak-samples.json`.
The soak VM's GLib, Shell, RDP and Sunshine binaries match the actual final
SquashFS binaries byte for byte (`soak-release-binary-comparison.json`).
Its only later image correction was automatic SVG loader cache initialization.

Shell input acceptance was repeated on the fresh release after removing a
temporary diagnostic extension. Earlier GUI tests had partial compositions
and sent boot markers to overview search instead of the text fixture. Those
failures did not recur after waiting for stable search focus, leaving overview
and explicitly focusing the RDP window for application input. No Shell or
Fcitx input patch was introduced for those failures. Test text windows use
non-unique application instances so an existing fixture cannot silently
receive a later launch intended for another output directory.

Compressed image size grew from 634,120,298 to 709,412,598 bytes
(+75,292,300 bytes, 71.80 MiB). Both raw images remain 8,724,431,360 bytes
because partition sizes are fixed. Logical regular-file payload grew by
280,553,365 bytes. See `image-footprint.json`.

Target acceptance still requires Intel GPU/encoder stability, headless and
KMS behavior, total RAM/idle CPU, 1080p/60 workloads, real Windows/macOS RDP
and Moonlight clients, and physical router regression checks. VM results
do not establish these outcomes.

The original active `.config` was restored byte for byte after validation.
The three repository heads, stashes, indexes and 62 original overlay files
were preserved. Both disposable VMs shut down cleanly and their private
RDP/Xvfb/audio fixtures were stopped; existing host VMs remained running.
That VM-only run did not publish feeds or install packages on the physical
device; the subsequent deployment is recorded separately above.

## Source and package checks

```sh
python3 scripts/tests/test-custom-package-updates.py
python3 scripts/tests/test-gnome-rdp-listener.py
python3 scripts/tests/test-gnome-keyring.py
python3 scripts/tests/test-sunshine-gnome.py
python3 scripts/tests/desktop-rdp-config.py
python3 scripts/tests/test-desktop-ime.py
python3 scripts/tests/test-desktop-audio.py
git diff --check
git -C feeds/packages diff --check
git -C feeds/video diff --check
```

Check shell syntax and Python compilation for the new integration helpers.
Build every selected package, then the complete firmware with the normalized
GNOME profile. Audit the installed package manifest, udev rules, PAM files,
system/user units, portal choice and IM modules. Verify the migration adds no preset
RDP credentials, private TLS keys or keyring bootstrap secret to the image.
Record exact source/feed commits, image hash, configuration and build logs.
Restore the original active `.config` after validation.

After building, run `scripts/tests/gnome-desktop-runtime.js` with target GJS.
In the guest, set both `GI_TYPELIB_PATH` and `LD_LIBRARY_PATH` to
`/usr/lib/gnome-shell:/usr/lib/mutter-51`
and invoke `gjs gnome-desktop-runtime.js`. This loads the actual GTK4,
libadwaita, calendar, accessibility, Mutter and Shell classes and checks their
transitive typelib dependencies. It does not start a graphical session.

Run `gjs gnome-desktop-https.js` as the desktop user to verify the GIO TLS
backend, trusted HTTPS metadata and ZIP download from extensions.gnome.org.
This downloads Kimpanel for GNOME 51 without installing it. A `gio info
https://...` failure alone does not diagnose TLS: HTTPS file operations also
need a GVfs HTTP backend, while Shell uses libsoup directly.

Launch `nautilus /home/USER` in that user's Wayland session and verify a
visible file window, directory navigation and filename search. Repeat without
the optional `org.freedesktop.Tracker3.Miner.Files` schema to cover the
minimal profile's startup path; a process version query alone is insufficient.

## Disposable VM

Use a new Q35/UEFI VM with four vCPUs, 6 GiB memory and a disposable disk.
Give it a private network and loopback-only host forwards. Use a virtual DRM
display, keyboard/tablet and emulated audio. Do not modify existing domains,
host audio configuration or physical devices. Check both VirGL and a software
rendering path, and identify which path actually ran from renderer evidence.

`scripts/tests/gnome-desktop-vm.py --raw IMAGE --out PRIVATE_DIRECTORY`
starts the isolated firmware through a qcow2 overlay. Its stdin/stdout use
JSON lines for serial commands, reboot and reconnect operations; EOF stops
only its own QEMU process. Add `--renderer virgl` for the GPU-backed run.
SSH and RDP forwards default to loopback ports 22295 and 23389. No existing
libvirt domain is used.

For Moonlight UDP transport, add `--lan-udp`. With the available slirp
implementation, restricted LAN networking drops UDP replies even for a
plain forwarded echo test. This option permits replies on the test LAN;
WAN networking remains restricted and every host listener remains bound
to loopback. Verify that the guest has no default route through its test
LAN before exercising the client. Keep this VM harness issue separate
from Sunshine transport behavior.

Provision a private test account after first boot. Do not store its password
in tracked files. Configure desktop/RDP/Sunshine with the installed helpers.
Pin the RDP TLS fingerprint in the client and retain actual client logs.
After provisioning, run `python3 gnome-desktop-guest.py --user TEST_USER
--lan-address 192.0.2.1` inside the guest and retain its JSON output.
This records session ownership, Shell/remote/input unit PIDs, keyring state,
Mutter monitor response and listener bindings. It checks prerequisites for
the client tests below; it does not establish their acceptance.

`scripts/tests/desktop-client-audio.py --out NEW_PRIVATE_DIRECTORY --self-test`
checks the client audio fixture with a 1 kHz signal and verifies that its
graph contains no physical devices. Run it without `--self-test` and keep
stdin open for the RDP tests; `client-env.json` supplies the private runtime
environment. Playback uses `rdp-playback`, microphone input uses
`rdp-microphone.monitor`, and `tone.wav` can be played into `rdp-microphone`
with `pw-play`. Sending `{"quit": true}` stops the fixture's own processes.
The fixture's self-test is separate from successful RDP signal transport.

`gnome-desktop-input.py --gtk 3|4 --out PRIVATE_DIRECTORY` runs an actual
GTK text view and records committed text, key events and its process ID.
Its private `command.json` accepts clipboard copy/read requests. Use actual
client keyboard events to test input; writing fixture state is not an input
test. Retain candidate screenshots alongside the committed-text evidence.

| Required check | Evidence |
| --- | --- |
| One local/RDP/Moonlight session | Same user, logind session, Shell PID, application PID and changing test surface across all three paths |
| Ordinary-user isolation | UID/GID, seat/VT, PAM session and device ACLs; SSH session remains usable |
| Local input and RDP/Moonlight input | Real key/pointer input changes the shared application |
| RDP clipboard | Unicode text copied both ways, including `你好abc`; preserve the clipboard across reconnect |
| RDP playback | Known audio signal recorded at the client with nonzero RMS and expected frequency |
| RDP microphone | Client-injected known signal recorded inside the shared session; frequency and RMS verified |
| Chinese input | Enter `你好abc` with candidate popup visible in Shell, GTK3, GTK4, Firefox and an Xwayland application |
| Reconnection | Ten disconnect/reconnect cycles for each remote protocol; session and application PIDs persist |
| Concurrent remotes | RDP and Moonlight overlap without replacing the local session or losing input/audio |
| LAN changes | Listener follows the new address and closes the old one; Shell/application PIDs persist |
| Startup persistence | Three real VM boots; no local login; keyring, RDP auth, Sunshine pairing and capture permission work |
| Soak | Thirty minutes of streaming with frame/audio checks, logs and resource samples |
| Router regressions | WAN/LAN DHCP/DNS, netifd, firewall/NAT, procd services, SSH and package/kernel lifecycle smoke checks |

Exercise invalid RDP credentials and unavailable LAN/keyring conditions as
well as successful connections. Do not infer capture, microphone or Chinese
candidate acceptance from systemd `ActiveState`, an open port, or screenshots
of an otherwise idle desktop.

## Measurements and report

Compare baseline and GNOME firmware compressed/uncompressed sizes and installed
package footprint. Sample system memory, session process PSS/RSS, idle CPU,
and CPU during the same 1080p/60 stream workload. Record codec, encoder,
resolution, bitrate, received frames, dropped frames, frame gaps, latency
method and limitations. A receiver's input-to-frame measurement excludes
presentation latency unless the test includes the client display.

Physical target measurements remain separate: GPU driver/encoder stability,
headless behavior, RAM budget, image growth and streaming performance must be
measured on the actual hardware before deployment acceptance.
