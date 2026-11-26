# Desktop and remote audio

The x86_64/glibc native-systemd desktop uses per-user PipeWire and WirePlumber.
`pipewire-pulse` serves PulseAudio applications; `pipewire-alsa` serves ALSA
applications. The audio server's sockets stay in the user's private runtime
directory. There is no network PulseAudio listener.

`openwrt-desktop-audio` (`1-r9`, depending on `openwrt-desktop-base`, `rtkit`,
and PipeWire) serves both the GNOME 51 and KDE Plasma 6.8.3 desktops. Merge
`configs/desktop-audio.config` into the existing build configuration (or select
the `audio` component in the offline installer ISO) and run `make defconfig`.
This adds audio services, common codecs, RDP audio and Sunshine. Preserve the
rest of the configuration. Feed snapshots are recorded in
`configs/feed-mirrors-snapshot.json`. HDA/HDMI and USB audio drivers are supplied
by the existing desktop kernel configuration.

## Enrollment

Create an ordinary account, set its password, and configure it with
`desktop-setup USER`. Then run as root:

```sh
desktop-audio-setup USER
```

This grants playback and physical microphone access through the `audio` and
`audio-capture` groups. Per-user device ACLs also cover user managers which were
already running before enrollment, without restarting unrelated sessions or
containers. Boot and sound-device events converge ACLs through
`80-openwrt-desktop-audio.rules` and `openwrt-desktop-audio-acl.path`/`.service`,
which run the locked `/usr/libexec/desktop-audio-permissions` helper (clearing
any previous user's ACL and updating its state atomically).

Restart the desktop when ready to activate its RDP audio settings:

```sh
/etc/init.d/desktop restart
```

The account's PipeWire sockets and WirePlumber service start automatically on
native-systemd logins. `systemd-udev` installs upstream `78-sound-card.rules`
so ALSA cards receive `SOUND_INITIALIZED=1` natively without downstream
`pipewire` udev workarounds. In a desktop terminal, use `wpctl status`, `pactl info`,
`pw-play FILE.wav`, and `pw-record RECORDING.wav`. Select the output/source and
volume with `wpctl`; the normal output is preferred, with a virtual fallback
when there is no sound device.

RDP audio behavior depends on the active desktop session:

- **GNOME (`gnome-remote-desktop`)**: transports desktop playback as Opus at
  48 kHz when the client offers it, otherwise as AAC or PCM at 44.1 kHz, and
  exposes a separate **RDP client microphone** source when microphone
  redirection is enabled by the client. Select that source in the recording
  application; it is not automatically played through speakers.
- **KDE Plasma (`krdp`)**: includes `001-add-rdpsnd-pipewire-playback.patch`,
  capturing the PipeWire default sink monitor as 48 kHz stereo S16 PCM and
  streaming playback over FreeRDP 3 RDPSND (no microphone redirection).

Clients without audio redirection continue to share the desktop normally.

Upstream `gnome-remote-desktop` drops queued playback whenever the client's
reported latency exceeds 300 ms. That figure includes the client's output-device
latency, so a device claiming e.g. 500 ms caused a flush loop and roughly half
of the audio was lost even on a sub-millisecond LAN. Patch
`005-ignore-constant-audio-device-latency.patch` compares recent reported render
latency against the minimum seen over two consecutive five-second buckets.
Audio is dropped only when the reported latency grows more than 300 ms above
that baseline. A steady 520 ms report therefore does not trigger flushing;
increasing delay still does. After a switch to a slower output device, drops
can continue for up to 10 seconds until the baseline adapts. This is a heuristic:
an acknowledgment does not identify which part of the delay is the device,
client queue or transport.

Missing confirmations alone do not trigger flushing. The former oldest-block
check could repeatedly discard all newly captured audio for almost two seconds
because one confirmation was missing, even while later blocks were confirmed
normally. The existing 50 ms local-frame age limit remains in force. The
baseline resets when the stream lock is released. Run
`python3 -B scripts/tests/test-gnome-rdp-audio-latency.py` to exercise the patched
C policy, including steady high latency, missing and delayed confirmations,
increasing delay, device changes and stream resets.

Upstream gnome-remote-desktop prefers AAC over Opus. Patch
`006-prefer-opus-playback.patch` reverses that order. An AAC packet holds 1024
frames at 44.1 kHz (23.22 ms). The PulseAudio backend of FreeRDP 3.33.0 (Remmina,
`xfreerdp`) adds each packet's duration in whole milliseconds (23 ms) to its
estimate of when playback ends. The estimate falls 0.94 % behind, and the client
then inserts silence as long as its whole `latency:` buffer. With `latency:60`
that was a 60 ms gap about every 6.5 s; with `latency:200`, a 200 ms gap about
every 21 s. The server delivers the full rate in both cases. An Opus packet is
exactly 20 ms, so this rounding loses nothing. FreeRDP 3.33.1 checks the real
stream queue before inserting silence. Clients that offer only AAC or PCM still
get 44.1 kHz. With such an older FreeRDP client, `sound=local` with
`rate:48000` (Remmina `audio-output=sys:pulse,rate:48000,...`) also forces Opus.

## Optional SSH audio stream helper

For ad-hoc remote monitoring without RDP or Moonlight, `desktop-audio-stream`
can pipe desktop output over SSH to FFplay on a client machine:

```sh
ssh -T USER@ROUTER desktop-audio-stream | ffplay -nodisp -autoexit -fflags nobuffer -f s16le -ar 48000 -ch_layout stereo -i -
```

The helper sends the default output monitor as stereo 48 kHz, 16-bit PCM.
Closing the SSH connection stops capture. The streams have separate clocks and
no guaranteed audiovisual synchronization. Use RDP or Moonlight for integrated
remote audio. On Windows, use a shell which preserves binary pipeline data
(such as PowerShell 7.4+ or a Unix-compatible shell).

## Sunshine and Moonlight

Sunshine (`2026.914.233613-r17`, depending on `openwrt-desktop-audio`) is
source-built without a system tray, using the tree's target libraries. It
captures the active GNOME or KDE Plasma Wayland display via `xdg-desktop-portal`
by default (`--capture=portal`), or optionally via KMS (`--enable-kms`), and
supports VAAPI encoding on compatible graphics hardware with software encoding
as a fallback. Its audio capture uses `pipewire-pulse`, and Moonlight audio uses
Opus.

Explicitly enroll the already-configured desktop user as root:

```sh
sunshine-setup USER --capture=portal
# Or opt in to KMS capture instead of portal capture:
# sunshine-setup USER --enable-kms
```

Portal capture avoids elevated capture privileges (`sunshine_capture='portal'`
in `/etc/config/desktop`). Opting into `--enable-kms` grants the executable
`CAP_SYS_ADMIN` (permitted), restricts execution to enrolled users, and grants
the selected user virtual-input access to `/dev/uinput`. Installation alone does
not grant KMS capabilities; switching back to `--capture=portal` removes them.
Boot and package upgrades reapply permissions only after explicit enrollment.
`/dev/uinput` hotplug events are handled by `80-openwrt-sunshine.rules` and
`openwrt-sunshine-uinput.path`/`.service`, which invoke
`sunshine-permissions --uinput-only` so device events update only `/dev/uinput`
ACLs and never touch `/usr/bin/sunshine` or its KMS capabilities.

Start a new desktop session, then open `https://ROUTER-LAN-IP:47990`, create Web
UI credentials and pair Moonlight. Credentials and pairing remain in the user's
Sunshine configuration. `sunshine.service` (`PartOf/WantedBy=graphical-session.target`)
is supervised by `openwrt-desktop-services.service` across both GNOME and KDE
Plasma; its launcher binds Sunshine to the current LAN IPv4 address and disables
UPnP.
On single-render-device Intel `8086:4e61` hosts, the launcher disables HEVC
and AV1 probing and advertisement to avoid the observed iHD HEVC video-engine
hang. H.264 hardware encoding remains available. This is a device-specific
workaround, not a fix to the underlying Intel driver; other GPUs and multi-GPU
hosts retain their normal codec settings. User configuration and pairing files
are not rewritten.
Use Moonlight's **play audio on host** option to retain local playback while
streaming. The default audio target is stereo, 48 kHz.

## Applications and compatibility

Common media playback covers PCM/WAV, MP3, AAC, Opus, Vorbis and FLAC. Firefox
uses `libpulse`; GStreamer applications and SPICE viewers use the Pulse plugin
with audio conversion/resampling and the required format plugins. Flatpak
applications need their normal `--socket=pulseaudio` permission; application
codec availability inside a Flatpak still depends on its own runtime.

Recording covers local microphones and GNOME RDP microphone redirection. RDP,
Sunshine, and the optional SSH stream helper provide remote playback. Bluetooth,
JACK, and surround routing are not part of this integration.
Optional [direct QEMU-to-PipeWire audio](libvirt.md#direct-host-pipewire-audio-optional)
has a separate build switch and per-user access setup. SPICE console audio uses
the viewer's existing Pulse compatibility path.
