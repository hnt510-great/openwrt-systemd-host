# Audio in the shared GNOME desktop

The x86_64/glibc native-systemd desktop uses per-user PipeWire and WirePlumber.
`pipewire-pulse` serves PulseAudio applications; `pipewire-alsa` serves ALSA
applications. Sockets remain in the user's runtime directory.

## Enrollment and inspection

Create the ordinary account and configure its GNOME session with
`desktop-setup USER`. As root, enroll audio access:

```sh
desktop-audio-setup USER
```

The helper grants the required playback/capture access. Setup preserves the
user's existing audio and application settings. A desktop restart closes its
applications; restart only when ready to activate session changes.

Inside the user's desktop terminal:

```sh
wpctl status
pactl info
pw-play FILE.wav
pw-record RECORDING.wav
```

The account's PipeWire sockets and WirePlumber service start automatically on
native-systemd logins. Select the output/source and volume with `wpctl`;
the normal output is preferred, with a virtual fallback when there is no
sound device. HDMI device identifiers can change; use the current PipeWire
device list.

RDP transports desktop playback as PCM (48 kHz, with 44.1 kHz negotiation) and exposes a separate **RDP client microphone**
source when microphone redirection is enabled by the client. Select that source
in the recording application. It is not automatically played through speakers.
Clients without audio redirection continue to share the desktop normally.

Upstream gnome-remote-desktop drops queued playback whenever the client's
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

Sunshine shares the GNOME session. Portal capture uses the GNOME portal and
PipeWire; an initial screen-selection grant may be needed. Explicit KMS
capture uses a different permission path:

```sh
sunshine-setup USER --enable-kms
```

KMS enrollment grants the executable its capture capability and the user
virtual-input access. Use the portal enrollment described in the
[GNOME guide](gnome-desktop.md) when portal capture is desired.

Open Sunshine's LAN Web UI, set credentials and pair Moonlight. Pairing and
configuration remain in the user's profile. Sunshine follows LAN listener
changes and the session lifecycle. Its audio uses the PulseAudio compatibility
server. The Intel `8086:4e61` workaround restricts the affected device's codec
probing to H.264; other devices require their own validation.

## Applications and evidence

Firefox, GStreamer and SPICE viewers use their packaged audio integrations.
Flatpak applications require their normal audio permissions and runtime codecs.
[Optional QEMU-to-PipeWire audio](libvirt.md#direct-host-pipewire-audio-optional)
has separate per-user access setup. Bluetooth, JACK, surround routing and
recovery-mode audio are outside this integration's documented scope.

See [current audio validation](desktop-audio-validation.md) for VM and physical
measurements. Verify playback, microphone redirection, capture backend and
restart persistence separately for the actual client and hardware.
