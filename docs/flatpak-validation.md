# Flatpak integration validation

## Bazaar system repository compatibility — 2026-11-21

After successful r7 authentication, the helper added Flathub but Bazaar 0.9.9
segfaulted in `dex-thread-pool` following null-`GFile` assertions. Its bundled
libflatpak could not read the system repository. Flatpak r8 uses the standard
`/var/lib/flatpak` host path backed by a tmpfiles-managed symlink to
`/srv/flatpak/system`. Bazaar's final app-specific override instead exposes the
direct `/srv/flatpak/system` path and sets `FLATPAK_SYSTEM_DIR` there, avoiding
Flatpak's inability to export paths through OpenWrt's `/var -> /tmp` symlink.
The package is `bin/systemd/packages/x86_64/base/flatpak-1.18.4-r8.apk`, SHA-256
`0acffcc2d5e9acafe3714ca7acbd50467610a48c771542b115f864e1039d3892`.

| Check | Result |
| --- | --- |
| Crash reproduction | r7 accepted the desktop password and added the system remote; Bazaar then exited with status 11 and a worker-thread segfault |
| Package build and installation | r8 compiled and passed signature verification; simulation and installation changed only r7 → r8 |
| Repository path | Host `flatpak --installations` reports `/var/lib/flatpak`; the symlink resolves to `/srv/flatpak/system`; the temporary diagnostic bind mount was removed |
| Override preservation | Existing Bazaar override was saved before editing; its original host/Flatpak filesystem entries were retained in the final compatibility profile |
| Sandbox access | `FLATPAK_SYSTEM_DIR=/srv/flatpak/system` is visible and the system repository config is readable inside Bazaar's sandbox |
| GNOME smoke test | Bazaar remained running for more than 60 seconds with no segfault or null-`GFile` assertions; the Flathub system remote remained configured |
| Router health | D-Bus and polkit stayed active, no failed units appeared and the temporary uploaded APK was removed |

Scope: the test launched the real Bazaar UI in the existing GNOME session, but
did not click through an application installation or removal. Missing entry
cache warnings remained nonfatal and are separate from the crash. No VM or new
firmware image was built, no device was flashed and no feed publication was
performed. Evidence in the dated workspace includes the original crash and
override, the final override, r8 build/signature records and the post-launch
process, sandbox and journal checks.

## Flatpak sudo administrator authentication — 2026-11-21

The first Bazaar authentication attempt after the r6 update selected root.
The router's root account is locked, so PAM rejected the desktop password for
`org.freedesktop.Flatpak.configure-remote`. Flatpak r7 adds an earlier,
Flatpak-only polkit administrator rule selecting the existing `sudo` group;
unrelated polkit actions retain the root-only rule. The new signed artifact is
`bin/systemd/packages/x86_64/base/flatpak-1.18.4-r7.apk`, SHA-256
`39a720a7e1fe7417dbbed576201cbbcffd9a08d179d50542711b6cda659d1175`.

| Check | Result |
| --- | --- |
| Rule evaluation | Flatpak `configure-remote` resolves to `unix-group:sudo`; an unrelated power action still resolves to `unix-user:root` |
| Package build and signature | r7 compiled successfully; host and router signature verification passed; simulation upgraded only r6 → r7 |
| Router installation | r7 installed and polkit reloaded successfully; `05-openwrt-flatpak-admin.rules` is present |
| Prompt identity | A pseudo-terminal probe cancelled without password input displayed `Authenticating as: desktop-user`, not root |
| Helper and router health | Unprivileged system update discovery still returned `Nothing to update`; D-Bus and polkit stayed active, zero units failed and no APK journal remained |

Scope: no password was requested, read or entered by the validation commands.
The user must complete the actual Bazaar prompt with their desktop password.
No system remote was added and no system application was installed during this
check. As with r6 below, validation deployed only the exact signed userspace APK
to the physical router; no VM or firmware image was built or flashed. Evidence
is in the same dated workspace, including `router-auth-before.txt`,
`router-auth-r7.txt`, `build-r7.log` and the r7 checksum/signature files.

## System helper on the physical router — 2026-11-21

Flatpak 1.18.4-r6 enables the system helper for Bazaar and other clients of the
system installation. No new firmware image was built. The validated artifact is
`bin/systemd/packages/x86_64/base/flatpak-1.18.4-r6.apk`, SHA-256
`2312abb2bfaf7701979b154b24249ff650903164c8f90ebd6c55ebc5dd2b76b1`.

| Check | Result |
| --- | --- |
| Package build | `make -j16 package/custom/flatpak/compile V=s` passed; Meson reported `Build system helper: YES`, polkit-agent 128 and privileged group `root` |
| Host ITS lookup | `GETTEXTDATADIR` points host `msgfmt` at the target-staged polkit rules; the policy merged successfully |
| APK contents and identity | Helper, D-Bus activation/policy, systemd unit, polkit action/rules, sysusers data and fixed UID/GID 195 requirement present; version advanced past the published r5 ELF migration |
| Signature and simulation | Host and router signature verification passed; APK simulated only `flatpak` 1.18.4-r5 → 1.18.4-r6 |
| Router installation | Signed local APK installed successfully with the managed cache; post-install reloaded systemd and D-Bus |
| Unprivileged activation | `busctl ... org.freedesktop.DBus.Peer Ping` as UID 32769 activated `flatpak-system-helper.service`; the helper ran as root and D-Bus reported successful activation |
| Original update-discovery path | Repeated unprivileged `flatpak update --system --noninteractive` runs returned `Nothing to update` with exit status 0 instead of the missing-SystemHelper error |
| Existing integration | Six `test-flatpak-user-link.py` tests passed; needrestart reported Bazaar current |
| Router health | D-Bus and polkit remained active on their original PIDs, zero units failed and no pending APK transaction journal remained |

Scope: the router had no system remote or system-installed refs, so the update
check ended with `Nothing to update`. No system application was installed or
removed, no polkit authentication prompt was exercised, and Bazaar's graphical
UI was not manually clicked. This was a userspace helper activation change, so
runtime validation used the exact signed package and unprivileged caller on the
physical router rather than building and booting a VM image. No physical device
was flashed. Existing per-user applications were not changed, no feed
publication was performed, and only the verified local Flatpak APK was deployed.
The broader `test-apk-source-versions.py` run reported no Flatpak error, but the
suite failed with 17 errors for unrelated reserved releases in existing ppp,
nginx, ffmpeg, virtualization and other recipes; those recipes were not changed.

**Evidence:** `/srv/openwrt-validation/flatpak-system-helper-validation-20261121/`
contains the build log, package checksum/signature results, the original Bazaar
error excerpt and the post-install router checks.

## Ordinary-user desktop validation — 2026-10-12

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
| Runtime permissions | `fusermount3` 4755, bubblewrap 0755, `/dev/fuse` 0666; no system installation helper in this historical user-only validation (r6 enables it above) |
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
