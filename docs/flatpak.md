# Flatpak on the native systemd desktop

This package supports ordinary-user Flatpak applications on the
x86_64/glibc/native-systemd GNOME desktop. The GNOME and GTK portal backends
are packaged with the desktop integration. Applications retain their normal
sandbox permissions and runtime dependencies.

## Build

`configs/flatpak-feeds.json` records the packages and video feed bases and
commits. The incremental patches are
`patches/feeds/0003-packages-flatpak.patch` and
`patches/feeds/0004-video-flatpak.patch`. Keep the earlier local integrations
described in [local-build.md](local-build.md) and [firefox.md](firefox.md).
Apply these patches only to clean feeds at their recorded bases that do not
already contain the corresponding commits. This checkout already contains
both commits.

The nineteen additional selections from the validated build are saved in
`configs/flatpak.config`. Merge this fragment into the existing native-systemd
desktop configuration before normalizing it:

```sh
./scripts/kconfig.pl + .config configs/flatpak.config > .config.flatpak
mv .config.flatpak .config
make defconfig
```

Select `openwrt-flatpak` in Utilities and run `make defconfig`. It selects
Flatpak, OSTree, AppStream, the desktop portals and their dependencies.
`FUSE3_UTILS_SETUID` enables the setuid `fusermount3` helper for ordinary-user
document portal mounts. Bubblewrap remains non-setuid and uses user namespaces
and seccomp. No Flatpak system installation helper is installed.

Flatpak is built with `-Dxauth=enabled` (linked against `libXau`). GNOME
protects Xwayland with a per-session cookie file named by `XAUTHORITY`; with
X11 authorization support Flatpak writes a filtered copy of that cookie into
the sandbox for applications that use the `x11` socket (for example Steam).
Builds before `1.18.4-r4` passed `DISPLAY` without the cookie, so X11-only
applications could not authenticate to Xwayland.

Build the packages first, then the complete image:

```sh
make -j4 package/custom/openwrt-flatpak/compile V=s
python3 scripts/build-and-publish.py build-only -j4 V=s
```

The native firmware remains under `bin/systemd/targets/x86/64-glibc/`.
Do not treat successful package compilation as validation of that image.

## Account setup and applications

Create an ordinary account and password after flashing, as described in
[desktop.md](desktop.md). As root, configure its repository and desktop:

```sh
flatpak-user-setup alice
desktop-setup alice
```

`flatpak-user-setup` creates `/srv/flatpak/users/UID` with mode 0700 and links
`~/.local/share/flatpak` to it. Repository parents belong to root and must not
be writable by other users. It refuses to replace a nonempty repository,
an unexpected link or a repository belonging to another UID. Home-directory
changes run as the ordinary user. Setup is idempotent and does not download
applications or add remotes. The standard per-user XDG data directory is used;
custom `XDG_DATA_HOME` configurations need separate provisioning.

In that user's desktop terminal:

```sh
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak search --user calculator
flatpak install --user flathub org.gnome.Calculator
flatpak run --user org.gnome.Calculator
flatpak update --user
flatpak list --user
flatpak uninstall --user org.gnome.Calculator
flatpak uninstall --user --unused
```

Use `--user` for all management operations. Flatpak itself otherwise defaults
to system installation. Existing native applications, including Firefox,
are independent of these commands.

GNOME supplies the session display and D-Bus environment. The desktop
integration imports application export directories and connects the per-user
portal services to that session. The capability-clearing helper keeps inherited
capabilities from interfering with non-setuid bubblewrap. FUSE helpers retain
their configured permissions.

Launch applications from the ordinary user's graphical session. For diagnostics:

```sh
systemctl --user status xdg-desktop-portal xdg-desktop-portal-gnome xdg-desktop-portal-gtk
journalctl --user -u xdg-desktop-portal
```

## Storage and firmware upgrades

The repository uses the persistent overlay under `/srv`, not volatile `/var`.
Applications, runtimes and update downloads share the image's disk capacity.
The current root partition is 8 GiB; check `df -h /srv` before installing large
applications. A separately provisioned persistent data filesystem can be
mounted at `/srv/flatpak` before setup. This package does not repartition disks
or alter existing mounts.

Existing configuration-preserving upgrade backups include `/home`, including
`~/.var/app` personal data and the repository symlink. They do not follow that
link into `/srv/flatpak`, so applications and runtimes are not copied into the
configuration archive. A repository on the root overlay can be erased by a
firmware upgrade; a separate data disk must remain mounted to reuse its data.

Before upgrading, as each user:

```sh
mkdir -p ~/.config
flatpak list --user --app --columns=application,branch,origin > ~/.config/flatpak-apps.tsv
flatpak remotes --user --show-details > ~/.config/flatpak-remotes.txt
```

Keep the application list and remote details with your backup. After restoring
accounts and homes, run `flatpak-user-setup USER` again as root, add Flathub as
the user, and reinstall the listed applications/branches. Recreate any custom
remotes using their original trusted repository definitions. Runtimes are
downloaded automatically. Application personal data remains in `~/.var/app`;
repository-local overrides and portal grants need to be reapplied when the
repository is recreated.

Native systemd flashing remains guarded: use the GRUB procd-recovery entry and
the existing configuration-preserving upgrade procedure. See [systemd.md](systemd.md).
Upload the firmware to `/tmp` after booting recovery and verify its SHA256
before running `sysupgrade -T` and the actual upgrade. Keep a copy of the
configuration backup outside the device.

## Validation limits

Acceptance requires a freshly built image in an isolated VM: ordinary-user
installation and signature checks, Wayland GUI input, portal file grants,
reboot persistence, upgrade restoration and existing router/SSH/remote-desktop services.
VM rendering does not establish physical Intel GPU performance. Record actual
image size, disk usage and memory measurements with the validation report.
See [flatpak-validation.md](flatpak-validation.md) for the completed build,
VM acceptance results, measured resources and recovery-upgrade limitations.
