# Local desktop and LAN VNC

This image includes a lightweight Weston desktop and graphical terminal.
VNC mirrors one connected local display. The desktop defaults to GPU rendering
through EGL/GBM, allowing SPICE OpenGL consoles to import GPU buffers;
the existing Intel DRM driver handles the monitor. The desktop package does not provision accounts or supply passwords or TLS
private keys; local image overlays may provision existing accounts.

After flashing, connect a monitor and bring up the LAN. As root:

```sh
useradd -m -U alice
passwd alice
desktop-setup alice
```

Use an existing ordinary account instead of creating a new one if appropriate.
Images containing zsh use `/usr/bin/zsh` for root and newly created users.
The account must have UID >= 1000, a non-root primary group, a home, a login
shell, and an unlocked password.
Setup adds the `video` and `render` groups; sudo access remains a separate choice.
The desktop starts automatically on subsequent boots when a display and LAN
address are available. The terminal and VNC session run as this user, with terminals starting in the home directory.
Click the terminal icon in the top panel to open a terminal window.

Images with `openwrt-desktop-launcher` also provide an Applications grid icon.
Click it to search installed graphical applications by name or keyword. Use
the arrow keys and Enter to launch an application, or Escape to close the
window. Native and exported Flatpak desktop entries appear automatically;
personal desktop-entry overrides and visibility settings are respected.
The launcher runs as the desktop user and supports the configured Chinese
input method. Existing terminal, Firefox and virt-manager panel shortcuts remain.

Images containing Firefox ESR also show a browser icon in the panel.
Click it to browse as the desktop user; Firefox does not start automatically.
See [Firefox setup, updates and profile backups](firefox.md).

Images with `openwrt-flatpak` support ordinary-user Wayland applications from
Flathub. See [Flatpak setup, storage and upgrades](flatpak.md).

Images with `openwrt-appimage` run manually downloaded AppImages as the desktop
user, including X11 applications through Xwayland. See [AppImage launch and
offline dependency bundles](appimage.md).

Connect a TLS-capable VNC viewer, such as [TigerVNC](https://tigervnc.org/doc/vncviewer.html), to `LAN_IP::5900`.
Authenticate with the desktop account's username and password. Use a client
that supports VeNCrypt/X509Plain, rather than a password-only VNC client.
To verify the certificate, copy the public certificate to the client:

```sh
scp alice@LAN_IP:/etc/desktop/tls/alice.crt ./openwrt-desktop.crt
vncviewer -SecurityTypes X509Plain -X509CA openwrt-desktop.crt LAN_IP::5900
```

Compare its SHA256 fingerprint with the fingerprint printed by setup using
an independently trusted SSH connection. The certificate includes the LAN
IPv4 address at setup time. If that address changes, stop the service and
move its certificate and key aside before rerunning setup to issue a new pair;
update the client's trusted certificate. Private keys must remain private.

The service binds to the LAN IPv4 address and does not add firewall rules.
Connections follow the existing firewall policy for that destination.
TLS credentials, desktop configuration, and the existing account/home
preservation rules survive upgrades that retain configuration.

Settings are in `/etc/config/desktop`; ports must be in the range 1024–65535.
To choose a specific connected display:

```sh
ls /sys/class/drm/
uci set desktop.main.output='HDMI-A-1'
uci commit desktop
/etc/init.d/desktop restart
```

To lower the shared desktop resolution, select a mode supported by the monitor:

```sh
uci set desktop.main.mode='1280x720'
uci commit desktop
/etc/init.d/desktop restart
```

This changes the physical monitor and both remote mirrors. `mode` defaults to
`preferred`; it also accepts `WIDTHxHEIGHT` or `WIDTHxHEIGHT@REFRESH`. Save open
work before restarting the desktop. The setting persists across boots.

## Optional live desktop sharing over RDP

Images built with `WESTON_RDP` include FreeRDP 3 and the native Weston RDP
backend. RDP shares the same local desktop and applications as VNC. Configure
the ordinary desktop account first, then run as root:

```sh
desktop-setup alice
desktop-rdp-setup alice
```

The second command prompts twice for a separate, nonempty RDP password.
Enabling RDP for the first time restarts the desktop and closes its applications;
save work first. Subsequent password changes do not restart the desktop.
Use the desktop username and this RDP password, rather than the Linux login
password. Changing the Linux password does not change the RDP password.
Existing authenticated connections remain connected until disconnected.

Connect Windows Remote Desktop (`mstsc`) to `LAN_IP:3389`, or choose RDP/NLA
in Remmina. For FreeRDP 3 on Linux:

```sh
xfreerdp3 /v:LAN_IP:3389 /u:alice /sec:nla /cert:tofu
```

Enter the password at the client prompt. Verify the certificate fingerprint
printed by setup through a trusted SSH connection before accepting it. For
managed clients, trust the public desktop certificate instead of accepting
an unverified certificate. NLA is mandatory; anonymous TLS and legacy RDP
security are rejected. Only the user running the desktop may connect.

RDP binds to the LAN IPv4 address and retains the local monitor's resolution.
It uses Weston's RemoteFX/NSCodec or bitmap encoding and defaults to 30 Hz;
delivered frame rate and latency depend on CPU, resolution, client, and network.
It supports screen sharing, keyboard/mouse control, and clipboard text. VNC
remains available. The service requires a connected monitor and does not
create independent remote login sessions. Optional [desktop audio](desktop-audio.md)
adds RDP playback and microphone redirection, plus an SSH audio stream for VNC.

Additional settings in `/etc/config/desktop` are:

| Option | Default | Meaning |
| --- | --- | --- |
| `rdp_enabled` | `0` | Enable after setting the RDP password |
| `rdp_port` | `3389` | LAN TCP port, 1024–65535, different from VNC |
| `rdp_refresh_rate` | `30` | Refresh rate, 1–60 Hz |

The private NTLM credential file is `/etc/desktop/rdp/USER.sam`, owned by the
desktop user with mode 0600. It is preserved with `/etc/desktop/` during upgrades
that retain configuration. The RDP package supplies no preset RDP password, credential hash, or private
TLS key. Configuration changes require a
desktop restart. To disable RDP and retain VNC:

```sh
uci set desktop.main.rdp_enabled='0'
uci commit desktop
/etc/init.d/desktop restart
```

On native systemd, read Weston logs with `journalctl _UID=$(id -u alice)`;
in procd recovery, use `logread -e weston`. See
[RDP build and runtime validation](desktop-rdp-validation.md) for tested
behavior and performance boundaries.

With `output=auto`, the first connected DRM connector in pathname order is
shared. Other monitors can be separate local outputs. Remote resizing is
disabled for the mirrored display. Keep a monitor connected; this service
does not create a remote-only desktop.

For recovery or to release the display:

```sh
uci set desktop.main.enabled='0'
uci commit desktop
/etc/init.d/desktop stop
logread -e openwrt-desktop
logread -e weston
```

SSH and LuCI remain available when the desktop is stopped. Missing accounts,
passwords, monitors, seatd, or LAN addresses prevent session startup. Crashes
are retried five times with a delay, then reported by procd.

## GPU desktop for SPICE GL

The default compositor renderer is `gl`. `desktop-setup USER` grants the
render-node access it requires. Existing saved configurations retain their
renderer on package upgrades; migrate an existing `pixman` desktop as root:

```sh
uci set desktop.main.renderer='gl'
uci commit desktop
/etc/init.d/desktop restart
```

Reconnect and restart desktop applications. Weston uses EGL/GBM on the local
DRM device, and the authenticated TLS VNC mirror remains available. EGL
startup failures stay in the desktop service log; there is no automatic
software fallback. To return to software composition, set the option to
`pixman` and restart. Software composition cannot import the SPICE GL buffers
in the tested Intel setup; disable SPICE OpenGL when using it. Configurations
without `renderer` use GL. The option is passed identically by systemd and
procd service paths.

## Complete-frame composition for Sunshine

The desktop defaults to `option force_composition '1'`, including existing
configurations without this option. The session exports Weston's built-in
`WESTON_FORCE_RENDERER=1` so client buffers are composed into the desktop
instead of assigned directly to hardware planes. This prevents windows such
as Firefox from disappearing or appearing black in Sunshine KMS capture.
GL composition, Firefox hardware video decoding and Sunshine hardware encoding
remain available. Hardware cursor planes are unaffected.

To apply the setting explicitly to an existing desktop:

```sh
uci set desktop.main.force_composition='1'
uci commit desktop
/etc/init.d/desktop restart
```

Restarting the desktop closes its applications and interrupts remote desktop
connections. Set `force_composition` to `0` and restart to restore client-buffer
scanout; the session unsets `WESTON_FORCE_RENDERER` because Weston treats any
value, including `0`, as enabled. Both systemd and procd use the same setting.

## Optional compositor capture for Sunshine

`desktop.main.sunshine_capture` accepts `kms` (default) or `weston`.
The optional `weston` route captures the composed output through
its PipeWire mirror instead of reading the DRM primary plane. Build with
`CONFIG_WESTON_PIPEWIRE=y`, `sunshine`, and `openwrt-desktop-audio` on the
native-systemd x86_64/glibc profile. The PipeWire video SPA plugin is required. Keep `force_composition=1` with
this route too: the physical test with direct scanout enabled produced stale
mirror frames. This option does not remove the composition requirement.

```sh
uci set desktop.main.sunshine_capture='weston'
uci commit desktop
/etc/init.d/desktop restart
```

This interrupts desktop applications and remote connections. The session starts
the user's PipeWire daemon before Weston and mirrors the configured physical
output. Sunshine explicitly selects `weston.pipewire`; it never silently falls
back to KMS. If the mirror is unavailable, local display, RDP and VNC remain
available, while Sunshine reports the capture error. After a PipeWire daemon
failure, restart the desktop to recreate the mirror. The procd recovery path
does not enable this backend.

To return to KMS, set `sunshine_capture='kms'`, keep
`force_composition='1'`, commit, and restart the desktop. KMS remains the
recommended default from the physical comparison; see
[capture validation](weston-launcher-capture-validation.md) for results and
remaining client acceptance checks.

## Chinese input

See [Chinese Pinyin and macOS RDP shortcuts](desktop-ime.md) for the optional
Fcitx5 integration and Ctrl+Shift+Space toggle.
