# Distrobox on the native-systemd host

The glibc desktop profile includes Distrobox 1.8.2.5 and the matching glibc
`getent` utility. Distrobox uses the existing rootless Podman runtime and
ordinary-user login session. It installs no additional boot service.

From a fresh login as the desktop user:

```sh
distrobox create --name debian --image docker.io/library/debian:13
distrobox enter debian
sudo apt-get update
sudo apt-get install jq
distrobox-export --bin /usr/bin/jq --export-path "$HOME/.local/bin"
exit
"$HOME/.local/bin/jq" --version
distrobox list
distrobox stop --yes debian
```

Guest `sudo` installs packages inside the container. Run the host Distrobox
commands as the ordinary user. For an account without rootless Podman setup,
an administrator can run `podman-rootless-setup USER`; reconnect afterwards.

By default Distrobox shares the user's home directory. Use
`distrobox create --home "$HOME/containers/debian-home" ...` to give a container
its own home directory. Distrobox integrates with the host and is intended
for trusted distribution images and applications.

For graphical applications, launch from the existing desktop session so that
`WAYLAND_DISPLAY`, `DISPLAY` and the user D-Bus environment are available.
Inside the container, install the application and run
`distrobox-export --app APPLICATION` to create its host desktop launcher.
`distrobox-host-exec COMMAND` runs a command back on the host using the existing
Flatpak user-session service. Upstream installs its pinned `host-spawn` helper
inside the guest; first initialization requires network access.

Build the userspace packages with:

```sh
make package/custom/glibc-getent/compile package/custom/distrobox/compile V=s
```

Run `scripts/test-distrobox.sh` from an ordinary-user login to exercise the
container lifecycle, shared files, DNS/HTTPS, guest packages, host commands,
and exported command arguments and exit status. It downloads Debian 13 and
removes its own container and temporary home on exit. `KEEP=1` retains the
named test resources for desktop tests; the script prints their paths.

The GTK fixture in `scripts/tests/distrobox-gtk-probe.c` is compiled and run
inside the guest to verify Wayland and Xwayland display/input integration.
It logs the selected backend and received input. Optional
`DISTROBOX_TEST_RESULT` and `DISTROBOX_TEST_SCREENSHOT` paths record the typed
marker and a GTK application capture after Enter or button activation.
See [validation results](distrobox-validation.md) for the tested artifact and
physical-router deployment boundary.
