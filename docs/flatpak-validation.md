# Flatpak integration validation — 2026-10-12

The supported configuration is x86_64, glibc and native systemd, with an
ordinary-user Wayland desktop. The acceptance application was the signed
Flathub `org.gnome.Calculator` stable release (51.0, GNOME runtime 51).
The test fixture `org.openwrt.PortalProbe` used the same runtime and only
Wayland/IPC permissions; its local unsigned remote was confined to the VM.

## Build and package checks

The package chain and complete systemd firmware were built with `make -j4`
and `V=s`. Package signatures were checked with the checkout's public APK
key, and all eight entries in the image directory's `sha256sums` passed.
The final combined UEFI image is 497592197 bytes (474.54 MiB), an increase
of 4722481 bytes (4.50 MiB) over the starting artifact. Its SHA256 is
`1d932bd3d22417fdcad115ed14bf504c1fc6d4d6f011f55afea7f4295f5f8f83`.
The last complete build took 4m56s with a peak compiler/build-process RSS of
about 2.03 GiB. The selected final packages include `openwrt-flatpak` 1-r5,
`libpipewire` 1.6.9-r3.
Compiler/linker flags were checked for host `/usr/include` and `/usr/lib`
leaks after correcting `libsystemd.pc`; the new libraries/modules have no
RPATH/RUNPATH pointing at host libraries.

All previously selected `.config` options were retained. Nineteen additional
options select the Flatpak stack and its prerequisites. Unrelated working
tree changes were retained. Changes span the main tree, `feeds/packages`
(GnuPG and FUSE), and `feeds/video`; deploy or archive
all three source trees together. Feed commit/base references and incremental
patches are recorded in `configs/flatpak-feeds.json`; the nineteen additional
build selections are in `configs/flatpak.config`.

The six `scripts/tests/test-flatpak-user-link.py` checks passed, covering
idempotence, existing data/hidden entries, empty directories, wrong links,
linked repositories and existing files. The GTK portal test source is
`scripts/tests/flatpak-portal-probe.c`.

## Isolated VM acceptance

The VM uses KVM/Q35, UEFI, 2 vCPUs, 4 GiB RAM, virtual DRM/USB devices and a
dedicated qcow2 disk. Its restricted LAN is separate from the host's network;
a second user-mode WAN provides download access. Test accounts, passwords,
SSH keys, remotes and applications exist only in the disposable guest.

| Check | Observed result |
| --- | --- |
| Runtime permissions | `fusermount3` 4755, bubblewrap 0755, `/dev/fuse` 0666; no system installation helper |
| User setup | Root account rejected; setup repeatable; UID repository 0700; repository link preserved |
| Flathub | Remote import with GPG verification enabled, search, install, update and uninstall/reinstall passed |
| Sandboxing | Calculator uses seccomp filter mode 2 and no effective capabilities; the desktop clears ambient/inherited capabilities |
| File authorization | GTK native Save dialog returned `/run/user/UID/doc/...`; authorized file written; unrelated host file and directory remained hidden before and after selection |
| Real update | PortalProbe commit changed and `/app/revision` became `revision-2`; the signed Calculator update check also passed |
| Desktop lifecycle | Independent user monitor starts portals, stops them after desktop termination and restores them on restart |
| Reboot | Accounts, TLS credentials, repository, applications and personal-data marker persisted; portals/display environment restored automatically |
| Router administration | LAN/WAN, NAT masquerading, WAN HTTPS, root/user SSH, authenticated LuCI login, status page and system-board RPC passed |

## Recovery upgrade

Native systemd rejected actual flashing while allowing image checks and
backups. The GRUB recovery entry ran procd as PID 1. A configuration-preserving
upgrade from an image placed directly in recovery `/tmp` wrote the complete
8 GiB root partition and automatically returned to systemd.
The EFI GRUB image includes the search and label-search modules needed to
locate the kernel partition after that recovery upgrade.

The configuration archive retained the account, repository symlink,
application list and `~/.var/app` marker without following the link into
`/srv/flatpak`. The root-overlay repository was erased by flashing.
`flatpak-user-setup` recreated it safely; adding Flathub and reinstalling the
applications restored functionality while preserving the personal marker.
Normal uninstall also preserved that marker. After flashing the final image,
the retained session and runtime files (session hook, capability helper, desktop launcher,
FUSE rule and PipeWire client config/protocol module)
matched both `/rom` and the final built rootfs. The final boot reported no
failed system units and no desktop startup retries.

An earlier trial using an intermediate guest image and staging firmware
under `/srv` failed during decompression and left the root partition incomplete.
The cause of that corruption was not isolated. The verified recovery procedure
uploads directly to `/tmp`, checks SHA256 and complete decompression, then runs
`sysupgrade -T` and `sysupgrade`. The automatic staging-copy path is not an
accepted result of this validation.

## Resource measurements and limits

Calculator plus GNOME 51 and the downloaded GL/locale extensions consumed
2634 MiB (about 2.57 GiB) of repository disk space. The 8 GiB root partition
had approximately 4.7 GiB available afterward. A measured Calculator sandbox
cgroup peak was 311107584 bytes (about 297 MiB, including charged file cache);
process high-water RSS was about 241 MiB. With the application active,
`free -m` reported approximately 463 MiB used and 3466 MiB available on the
3930 MiB guest, with no swap in use. These are VM workload measurements,
not limits for arbitrary Flatpak applications.

The software-rendered VM does not establish physical GPU performance,
physical display/USB hotplug behavior, or simultaneous multi-client input
arbitration. Hardware validation should include desktop startup and
network-interface transitions.

Settings/accessibility and `xdg_foreign` warnings remain outside the first
version's supported file-selection path. PipeWire client context creation
works, but there is no PipeWire daemon or audio/screen-sharing service.
At 1280×800, the GTK file chooser can extend beyond the bottom of the display;
entering a full destination and pressing Enter successfully accepted it.

Build/VM logs and screenshots are stored privately under
`/tmp/openwrt-flatpak-work/` and
`~/.local/share/openwrt-vm/20261012-flatpak/` on the build host.
The test VM was powered off; its QEMU process and all three forwarded ports
were confirmed stopped. The temporary password, askpass helper and private
SSH key were removed. Disk/backup artifacts remain private for inspection.
