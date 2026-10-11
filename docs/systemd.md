# Native systemd on OpenWrt

This experimental variant targets x86_64, glibc and APK. Enable
`CONFIG_OPENWRT_SYSTEMD=y`, run `make defconfig`, then build with `make`.
Firmware and APK repositories go to `bin/systemd`; the normal `bin/targets`
images remain available. Native and stock images use separate root staging
directories and rootfs caches, while sharing the cross-toolchain and downloaded
sources. Native x86 images use sparse padding and streaming gzip so image
generation does not allocate memory proportional to the padded disk-image size.

## Boot and service ownership

OpenWrt `/sbin/init` still mounts the early filesystems, runs preinit and mounts
the overlay. The normal GRUB entry passes `openwrt.init=systemd`, then init
checks the filesystem layout and executes systemd as PID 1. A failed preflight
falls back to procd. The `procd recovery` entry passes `openwrt.init=procd`;
the failsafe entry also retains procd. A command line without the selector
defaults to procd.

Systemd owns the system manager, native units, timers, sockets and journald.
`openwrt-ubusd.service` owns ubusd. `openwrt-procd.service` runs procd as a
service supervisor, hotplug and watchdog daemon, and reports readiness after
ubus registration and coldplug. `openwrt-services.service` runs enabled OpenWrt
rc scripts in order. Existing UCI, LuCI and `/etc/init.d/*` controls continue
to address procd-managed router services. D-Bus has a native unit and its rc
script is skipped in systemd mode. The rc shutdown unmount script is also
skipped so systemd can unmount filesystems after stopping services.
The bridge completes the rc sequence even if an optional script returns a
nonzero status, matching procd's rc queue, and reports that status in the
journal. An active bridge means the sequence completed; check individual
router services separately. Shutdown scripts use a bounded GNU timeout.
Console login uses the existing OpenWrt
login helper. Procd children stay in its delegated service cgroup.

OpenWrt retains netifd, firewall, DHCP/DNS, NTP, device events, module loading,
sysctl and logd. Udev, its generators, and systemd's competing sysctl/module
units are disabled. Native units should use explicit paths and service
dependencies; udev-backed `.device` dependencies are outside this integration.
`logread` retains router logs, while `journalctl` records native unit output.
Journald uses volatile storage limited to 32 MiB; systemd watchdog handling is
disabled so procd remains the watchdog owner.

The package excludes networkd, resolved and timesyncd. Native mode includes
polkit, PAM login sessions, logind and systemd user managers; see
[ordinary-user authorization and sessions](systemd-permissions.md). The SSH
generator is removed; the PAM variant of OpenWrt OpenSSH retains its listener
and configuration. Display/input device access still uses seatd.

## Filesystem and packages

Package payloads and root overlays are normalized to merged `/usr`: `/bin`,
`/sbin` and `/lib` become relative aliases for `/usr/bin`, `/usr/sbin` and
`/usr/lib`. `/run` is a real tmpfs and `/var/run` points to it. Package file
lists, conffiles and alternatives use canonical paths. Conflicting command
applets use OpenWrt alternatives, with BusyBox as the fallback. Unsupported
payload collisions fail the build instead of silently overwriting files.

Stock upstream APK repositories are commented out in this variant because
their payload layout is incompatible. Serve repositories from this build's
`bin/systemd` tree and configure `/etc/apk/repositories.d/customfeeds.list`.
Use matching native APKs for installation and upgrades. Keep the signing
key private; the firmware includes the public verification key.

## Administration and recovery

Install native units in `/etc/systemd/system`, then use `systemctl daemon-reload`
and `systemctl enable --now example.service`. Keep router service configuration
in UCI. Avoid adding a second native unit for an existing procd service.
Reboot, halt, poweroff and `ubus call system reboot` delegate to systemd in
native mode and retain the usual behavior in recovery.

`sysupgrade -l`, backup creation and `sysupgrade -T` remain available under
systemd. Actual flashing is rejected by both the sysupgrade shell entry point
and procd's ubus method. Boot the GRUB procd recovery entry to flash firmware.
`/etc/machine-id` is kept across upgrades. Test recovery access before deploying
to hardware.
The native variant loads the VFAT codepage modules during early boot so x86
preinit can retrieve the saved configuration from the EFI partition.

## Updating the source tree and feeds

The boot bridge lives in the main repository; PAM-enabled SSH and native
D-Bus support also have local changes in the packages feed, documented in
[permissions and sessions](systemd-permissions.md). The integration does not
change `scripts/feeds`. Preserve main-tree and feed-local changes when updating OpenWrt. This
checkout uses merge-based pulls (`pull.rebase=false`), preserving its existing
local commits and merge history. Review outstanding changes before updating:

```sh
git status --short
git pull --no-rebase
./scripts/feeds update -a
./scripts/feeds install -a
make defconfig
```

These commands assume local edits will not collide with upstream updates.
Committing this integration does not commit other main-tree edits or any
changes inside `feeds/`, which is ignored by the main repository. Each Git
feed has its own history and working tree. Inspect modified feeds with
`git -C feeds/NAME status --short` and save their changes separately before
updating them. Preserve `.config` and any private `files/` overlay separately;
they are also ignored by the main repository.

The normal feed update uses `git pull --ff-only`. For a feed with intentional
local commits, use `./scripts/feeds update -r NAME` to rebase those commits.
For tracked uncommitted edits, `./scripts/feeds update -s NAME` also autostashes
them. Back up the feed first: autostash does not save untracked files and
reapplying changes can conflict. Resolve conflicts inside that feed before
continuing; inspect `git -C feeds/NAME stash list` if restoration failed.
Then refresh its index with `./scripts/feeds update -i NAME` and reinstall
links with `./scripts/feeds install -a -p NAME`.

Do not use `scripts/feeds clean`, force updates (`-f`), or `git reset --hard`
to resolve local-change conflicts. Changing a feed URL can replace its
checkout, so save its local work before changing `feeds.conf*`. Upstream
force-pushes require a separate history review; rebasing is not automatically
safe in that case.

After updating, check that `CONFIG_OPENWRT_SYSTEMD=y` remains selected and
rebuild the native image. Upstream changes to procd, package payload handling
or x86 image rules may require conflict resolution and renewed boot/recovery
validation; a clean Git merge alone does not prove firmware compatibility.

## Validation

Host checks:

```sh
python3 -B scripts/tests/test-merge-usr.py
sh scripts/tests/test-alternatives.sh
scripts/checkpatch.pl --no-tree --no-signoff package/system/procd/patches/100-systemd-compatibility.patch
make package/system/systemd/compile V=s
make package/system/procd/compile V=s
make package/system/systemd-openwrt/compile V=s
make V=s
```

Validate a fresh firmware boot, PID 1, cgroup controllers, native units/timers/
sockets, journald and logread, ubus, router services, LuCI, APK transactions,
reboot and persistent machine ID. Separately boot procd recovery and failsafe.
QEMU user networking can validate VM service/network behavior, but cannot
prove physical NIC behavior, PPPoE or a hardware watchdog.

### Verified on 2026-10-10

The full build passed with a 4 GiB memory and 1 GiB swap limit. Original active
configuration selections, unrelated source changes and the normal firmware
images were preserved. The merged-filesystem tests, alternative installation/
removal tests and procd patch style checks passed.
`make defconfig` retained the existing weechat package dependency-cycle warning;
the full firmware build still completed successfully.

The rebuilt EFI image was cold-booted in an isolated KVM/UEFI VM with two
virtual NICs, two CPUs and 2 GiB RAM. These checks passed:

| Check | Result |
| --- | --- |
| Native boot | systemd PID 1; core native and router bridge units active |
| Native facilities | Timer, socket activation, memory/process limits and journald |
| Router services | LAN, local DNS, firewall, OpenSSH, ubus and logread |
| Service restarts | ubusd and procd restart; LAN, DNS and firewall recover |
| LuCI HTTP | Login form, login redirect and authenticated overview response |
| Native APKs | Signed lsof and ping removal/reinstallation; command alternatives restored |
| Upgrade safeguards | Native backup/image validation allowed; shell and ubus flashing rejected |
| Recovery upgrade | Actual procd-recovery flash completed and returned to systemd |
| Persistence | Machine ID, enabled native unit and SSH key survived the upgrade |
| Failsafe | Recovery shell, overlay access, EFI menu restoration and return to native boot |
| Disk metadata | Primary and backup GPT headers and partition-entry checksums valid |

The recovery upgrader emitted a nonfatal libmount overlay-remount warning;
the subsequent unmount, image write, backup restoration and reboot completed.
This is VM validation, not physical-device upgrade validation. Interactive
LuCI rendering was not tested because no browser surface was available.

Validated image:
`bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`

SHA-256:
`7298ffa7b118cec3b6c63dc1abb9567dd104c33cd22316d21286fc1e416f2053`

Build and guest logs are saved in
`/srv/openwrt-validation/systemd-validation-20261010/logs`; the VM disk and serial
artifacts are in the parent directory. The disposable VM was powered off
after validation.
