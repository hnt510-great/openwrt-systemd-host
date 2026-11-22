# Flatpak on the native systemd desktop

> Systemd is the sole normal init on current x86/64 images. References below
> to procd recovery or firmware flashing from the running system describe
> older images. See [current boot and migration guidance](systemd-only-plan.md).

This optional package supports ordinary-user and system-wide Flatpak
applications on the x86_64/glibc/systemd GNOME image. Applications can be
managed from a terminal or through a Flatpak-aware graphical software store.
The desktop integration covers Wayland windows and file selection through the
GTK desktop portal. Desktop audio and screen sharing require their separate
OpenWrt desktop packages and provisioning.

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
As of `xdg-desktop-portal` `1.22.1-r5`, `xdg-desktop-portal` extracts
`org.freedesktop.portal.Flatpak.xml` from the pinned Flatpak source archive at
build time and no longer pulls in the `flatpak` runtime on its own; GNOME can
therefore be built without Flatpak, while `openwrt-flatpak` explicitly pulls in
`flatpak`.
`FUSE3_UTILS_SETUID` enables the setuid `fusermount3` helper for ordinary-user
document portal mounts. Bubblewrap remains non-setuid and uses user namespaces
and seccomp.

Flatpak 1.18.4-r8 enables `flatpak-system-helper`, allowing software stores and
`flatpak --system` commands to manage the system installation. The helper runs
as root only while needed and is activated by D-Bus; do not enable or start
`flatpak-system-helper.service` manually. Its polkit policy permits active local
users to update signed applications and metadata, while installing, uninstalling
and changing protected configuration require administrator authorization.
For these Flatpak administrator prompts, `05-openwrt-flatpak-admin.rules`
selects members of the existing `sudo` group, so the password belongs to the
desktop account, not the normally locked root account. Other polkit actions
retain OpenWrt's root-only administrator rule. The package creates the
unprivileged `flatpak` account used to isolate the revokefs backend and installs
the helper's polkit and D-Bus policy. Package installation reloads systemd and
polkit, then sends D-Bus a non-disruptive `SIGHUP` so new activation files take
effect without restarting the message bus.

The compiled system installation path is the standard `/var/lib/flatpak`.
That path is a symlink to `/srv/flatpak/system`, keeping host tools, desktop
export paths and repository inspection on the same persistent storage. Because
`/var` points to volatile `/tmp` on OpenWrt,
`flatpak-system-repository.conf` recreates the symlink through
`systemd-tmpfiles` at boot and after package installation. Do not replace the
symlink with a separate repository. Sandboxed applications additionally need
the direct `/srv/flatpak/system` path described below, because Flatpak cannot
correctly export a `/var/...` path whose parent is a symlink.

Flatpak is built with `-Dxauth=enabled` (linked against `libXau`). GNOME
protects Xwayland with a per-session cookie file named by `XAUTHORITY`; with
X11 authorization support Flatpak writes a filtered copy of that cookie into
the sandbox for applications that use the `x11` socket (for example Steam).
Builds before `1.18.4-r4` passed `DISPLAY` without the cookie, so X11-only
applications could not authenticate to Xwayland.

Build the packages first, then the complete image:

```sh
make -j4 package/custom/openwrt-flatpak/compile V=s
make -j4 V=s
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

Use `--user` for per-account applications. Existing native applications,
including Firefox, are independent of these commands.

For applications shared by all accounts, use the system installation explicitly:

```sh
sudo flatpak remote-add --system --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
sudo flatpak install --system flathub org.gnome.Calculator
flatpak list --system
sudo flatpak update --system
```

The system repository is `/var/lib/flatpak`, a symlink to
`/srv/flatpak/system`. A graphical store may perform these operations through
polkit instead of `sudo`; its authentication prompt
must have an active agent in the desktop session. Diagnose helper activation
with `systemctl status flatpak-system-helper.service` and
`journalctl -u flatpak-system-helper.service -u dbus.service -u polkit.service`.
An inactive unit is normal while no system-installation request is pending.

### Bazaar system backend

Bazaar also uses its bundled libflatpak to read system repository metadata.
Set `FLATPAK_SYSTEM_DIR` and expose the direct persistent path in that app's
sandbox. Do not add `/var/lib/flatpak` or `/var/tmp` to its filesystem list on
this `/var -> /tmp` layout. To reproduce the validated OpenWrt compatibility
profile, first save any custom entries with `flatpak override --user --show
io.github.kolunmi.Bazaar`, then run:

```sh
# --reset removes existing Bazaar overrides; restore unrelated custom entries afterward.
flatpak override --user --reset io.github.kolunmi.Bazaar
flatpak override --user \
    --nofilesystem=host:reset \
    --filesystem='~/.var/app' \
    --filesystem=/srv/flatpak/system \
    --nofilesystem=host \
    --filesystem=xdg-data/flatpak \
    --env=FLATPAK_SYSTEM_DIR=/srv/flatpak/system \
    io.github.kolunmi.Bazaar
```

The `host:reset` entry also suppresses Bazaar's original `/var/...`
filesystem entries, which cannot be exported correctly through OpenWrt's
symlinked `/var`. The direct repository path preserves the same read/write
access that Bazaar declares for its system backend; it is not a global override
for other applications.

GNOME session setup exports the per-user and system Flatpak export directories,
display and session D-Bus address into `systemd --user`.
`desktop-flatpak-session` starts `openwrt-flatpak-session.target`, which is
ordered after `graphical-session-pre.target` and belongs to
`gnome-session.target`. Portal services are D-Bus-activated as needed; the GTK
backend handles file-selection dialogs and the document portal uses the
setuid `fusermount3` helper. Native udev rules provide `/dev/fuse` access.
SSH alone does not provide a graphical display; run applications from the
desktop terminal. For diagnostics use:

```sh
systemctl --user status xdg-desktop-portal xdg-desktop-portal-gtk
journalctl --user -u xdg-desktop-portal -u xdg-desktop-portal-gtk
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
link into `/srv/flatpak`, and do not include the system repository, so
applications and runtimes are not copied into the configuration archive. A
repository on the root overlay can be erased by a firmware upgrade; a separate
data disk must remain mounted to reuse its data. Back up system remotes and the
`flatpak list --system` application list separately before such an upgrade.

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
reboot persistence, upgrade restoration and existing router/SSH/VNC services.
VM rendering does not establish physical Intel GPU performance. Record actual
image size, disk usage and memory measurements with the validation report.
See [flatpak-validation.md](flatpak-validation.md) for the completed build,
VM acceptance results, measured resources and recovery-upgrade limitations.
