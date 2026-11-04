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

Select the intended sink/source and volume. HDMI device identifiers can change;
use the current PipeWire device list. GNOME's RDP service carries playback and,
when the client enables redirection, a separate remote microphone source.
Choose that source in the recording application.

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
