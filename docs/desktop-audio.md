# Desktop and remote audio

The x86_64/glibc native-systemd desktop uses per-user PipeWire and WirePlumber.
`pipewire-pulse` serves PulseAudio applications; `pipewire-alsa` serves ALSA
applications. The audio server's sockets stay in the user's private runtime
directory. There is no network PulseAudio listener.

Merge `configs/desktop-audio.config` into the existing build configuration and
run `make defconfig`. This adds audio services, common codecs, RDP audio and
Sunshine. Preserve the rest of the configuration. Feed changes are recorded in
`configs/desktop-audio-feeds.json`; apply those feature patches after the
existing local feed patches (including the Firefox FFmpeg changes). HDA/HDMI and USB audio drivers
are supplied by the existing desktop kernel configuration.

## Enrollment

Create an ordinary account, set its password, and configure it with
`desktop-setup USER`. Then run as root:

```sh
desktop-audio-setup USER
```

This grants playback and physical microphone access through the `audio` and
`audio-capture` groups. Per-user device ACLs also cover user managers which were
already running before enrollment, without restarting unrelated sessions or
containers. Boot and sound-device hotplug restore those ACLs.

Restart the desktop when ready to activate its RDP audio settings:

```sh
/etc/init.d/desktop restart
```

The account's PipeWire sockets and WirePlumber service start automatically on
native-systemd logins. In a desktop terminal, use `wpctl status`, `pactl info`,
`pw-play FILE.wav`, and `pw-record RECORDING.wav`. Select the output/source and
volume with `wpctl`; the normal output is preferred, with a virtual fallback
when there is no sound device.

RDP transports desktop playback as PCM (48 kHz, with 44.1 kHz negotiation) and exposes a separate **RDP client microphone**
source when microphone redirection is enabled by the client. Select that source
in the recording application. It is not automatically played through speakers.
Clients without audio redirection continue to share the desktop normally.

## VNC with SSH audio

VNC continues to carry display and input through its existing TLS connection.
On a Windows/macOS/Linux desktop with OpenSSH and FFplay, run this separately
as the same ordinary account:

```sh
ssh -T USER@ROUTER desktop-audio-stream | ffplay -nodisp -autoexit -fflags nobuffer -f s16le -ar 48000 -ch_layout stereo -i -
```

The helper sends the default output monitor as stereo 48 kHz, 16-bit PCM.
Closing the SSH connection stops capture. The streams have separate clocks and
no guaranteed audiovisual synchronization. Use RDP or Moonlight for integrated
remote audio. On Windows, use a shell which preserves binary pipeline data
(such as PowerShell 7.4+ or a Unix-compatible shell).

## Sunshine and Moonlight

Sunshine is source-built without a system tray, using the tree's target
libraries. It captures the existing Weston display through KMS and supports
VAAPI encoding on compatible graphics hardware, with software encoding as a
fallback. Its audio capture uses `pipewire-pulse`, and Moonlight audio uses Opus.

Explicitly enroll the already-configured desktop user as root:

```sh
sunshine-setup USER --enable-kms
```

KMS enrollment grants the executable the broad `CAP_SYS_ADMIN` permitted
capability, restricts execution to enrolled users, and grants the selected user
virtual-input access to `/dev/uinput`. Installation alone does not grant these
permissions. Boot and package upgrades reapply permissions only after explicit
enrollment.

Start a new desktop session, then open `https://ROUTER-LAN-IP:47990`, create Web
UI credentials and pair Moonlight. Credentials and pairing remain in the user's
Sunshine configuration. The user service follows the active Weston session;
its launcher binds Sunshine to the current LAN IPv4 address and disables UPnP.
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

Recording covers local microphones and RDP microphone redirection. The VNC SSH
companion and Sunshine provide remote playback. Bluetooth, JACK, surround
routing, direct QEMU-to-PipeWire audio and procd-recovery audio services are not
part of this integration. The existing recovery desktop remains available.
