# Local desktop and LAN VNC

This image includes a lightweight Weston desktop and graphical terminal.
VNC mirrors one connected local display. The desktop uses CPU rendering;
the existing Intel DRM driver handles the monitor. No desktop account,
password, or TLS private key is embedded in the firmware.

After flashing, connect a monitor and bring up the LAN. As root:

```sh
useradd -m -U -s /bin/ash alice
passwd alice
desktop-setup alice
```

Use an existing ordinary account instead of creating a new one if appropriate.
The account must have UID >= 1000, a non-root primary group, a home, a login
shell, and an unlocked password.
Setup adds only the `video` group; sudo access remains a separate choice.
The desktop starts automatically on subsequent boots when a display and LAN
address are available. The terminal and VNC session run as this user, with terminals starting in the home directory.
Click the terminal icon in the top panel to open a terminal window.

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
