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

Systemd owns the system manager, native units, timers, sockets, journald,
device events (udevd) and the hardware watchdog. `openwrt-ubusd.service` owns
ubusd. `openwrt-procd.service` runs `procd --systemd=units`: procd provides the
OpenWrt service API and hotplug handlers, while every instance an init script
registers runs as a transient `openwrt-SERVICE@INSTANCE.service`; see
[systemd supervision of OpenWrt services](systemd-native-supervision.md). procd
reports readiness after ubus registration and its first-boot udev coldplug.
`openwrt-services.service` runs enabled OpenWrt rc scripts in order. Existing UCI, LuCI and `/etc/init.d/*` controls continue
to address procd-managed router services. D-Bus and OpenSSH have native units
and their rc scripts are skipped in systemd mode. The rc shutdown unmount script is also
skipped so systemd can unmount filesystems after stopping services.
The bridge completes the rc sequence even if an optional script returns a
nonzero status, matching procd's rc queue, and reports that status in the
journal. An active bridge means the sequence completed; check individual
router services separately. Shutdown scripts use a bounded GNU timeout.
Console login uses the existing OpenWrt
login helper. Daemon executions run as transient services beneath per-service
slices; rc scripts and the few instances procd still starts itself occupy
scopes there. See [cgroup ownership and cleanup](systemd-cgroups.md).

An optional [service control bridge](systemd-service-bridge.md) exposes
individual openwrt@NAME.service controls, shared rc.d enablement and live
status through systemctl. It preserves the ownership and boot ordering above
and defaults to off.

OpenWrt retains netifd, firewall, DHCP/DNS, NTP, module loading, sysctl and
logd. udevd receives device events and forwards those with `/etc/hotplug.d`
handlers to procd; it installs no interface-renaming, firmware or
module-loading rules. systemd's competing sysctl/module units are disabled.
Native units should use explicit paths and service dependencies.
Journald owns `/dev/log` and collects syslog, kernel messages and native unit
output. In systemd mode, the log init script starts `logd -J` as a journal-backed compatibility
reader: `logread`, the existing LuCI System Log page and UCI log forwarding
continue to work. Recovery boots retain logd's original syslog/kernel readers.
Journald uses persistent storage on root/extroot with bounded disk usage; see
[journal storage and cleanup](journald.md). The systemd manager owns the
hardware watchdog (`RuntimeWatchdogSec=30s`); procd recovery keeps its own.

The package excludes networkd, resolved and timesyncd. Native mode includes
polkit, PAM login sessions, logind and systemd user managers; see
[ordinary-user authorization and sessions](systemd-permissions.md). The SSH
generator is removed; the PAM variant of OpenWrt OpenSSH runs under
`sshd.service`, retaining its configuration and PAM integration. Lifecycle and
normal-boot enablement use systemctl; procd recovery retains its independent
rc.d SSH setting. See [native OpenSSH](systemd-sshd.md).
Display and input device access uses udev tags and logind seats.

### Network readiness

netifd has no systemd wait-online provider, so `network-online.target` used to
be reached before netifd started. `openwrt-network-wait-online.service` now holds
the target until netifd reports the selected interfaces up, and the package pulls
the target into every boot: rootless Quadlets wait for it through
`podman-user-wait-network-online.service`, but user managers cannot pull in a
system target. The service runs after procd and does not wait for the rc
sequence. Units that are not ordered after the target, including
`multi-user.target`, are not delayed.

By default it waits for every autostart, statically configured interface whose
device is present, such as `lan`; a WAN, PPPoE or VPN outage does not hold LAN
services. Without static interfaces it waits for every autostart interface with
a present device. Dynamic children such as `wan_6` are ignored. It gives up after
120 seconds with a journal message naming the interfaces still down; the target
is still reached. Select interfaces explicitly with a drop-in, for example when
a unit needs the upstream link:

```sh
mkdir -p /etc/systemd/system/openwrt-network-wait-online.service.d
cat > /etc/systemd/system/openwrt-network-wait-online.service.d/wan.conf <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/libexec/openwrt-network-wait-online --interface lan --interface wan --timeout 90
EOF
systemctl daemon-reload
```

`--any` accepts one selected interface. Interface readiness does not prove DNS
or Internet reachability. Check the current selection without changing anything:

```sh
/usr/libexec/openwrt-network-wait-online --timeout 1
```

### Optional systemd components

Select these additional packages in menuconfig or `.config`, then build with
`make package/system/systemd/compile V=s`:

| Package | Commands and purpose |
| --- | --- |
| `systemd-hostnamed` | `hostnamectl`, hostname and machine metadata through D-Bus |
| `systemd-machined` | `machinectl`, container/VM registration and D-Bus activation |
| `systemd-nspawn` | `systemd-nspawn`, namespace containers and a container unit template |
| `systemd-coredump` | `coredumpctl`, crash collection helpers and units |
| `systemd-oomd` | `oomctl`, pressure-based OOM management |

These packages require the exact matching systemd package release because they
use its private shared library. Install the matching signed systemd APK together
with the optional packages. Reload systemd's unit files and D-Bus configuration
after installation; run `systemd-sysusers` for the component account files and
`systemd-tmpfiles --create /usr/lib/tmpfiles.d/systemd-nspawn.conf` for the
machine image directory. No router reboot is required for installing them.

Hostnamed starts on demand through D-Bus. Installing it preserves the current
hostname. OpenWrt still applies `system.@system[0].hostname` from UCI at boot;
`hostnamectl set-hostname` does not update that UCI setting. Keep the UCI value
in sync when intentionally changing the persistent router hostname.

Machined starts on demand through D-Bus. The nspawn template uses an isolated
network namespace; configure networking explicitly in a per-container unit
override or `.nspawn` file. It does not rely on systemd-networkd or systemd's
module-loading units. Test a disposable root filesystem before enabling a
container unit; installing the package does not create or start containers.

Coredump units and oomd are installed without boot activation. Crash collection
requires a deliberate kernel core-pattern and socket/service configuration;
installation preserves OpenWrt's current core pattern. Enabling
`systemd-coredumpd.service` uses the newer kernel socket interface when supported.
For oomd, inspect the existing `ManagedOOM*` properties before starting the
service and explicitly configure the slices it should monitor. Installing it
does not enable memory-pressure kills. `coredumpctl list` only shows crashes
already recorded by systemd-coredump.

## Filesystem and packages

Native images identify themselves in /etc/os-release (an alias of
/usr/lib/os-release) as **OpenWrt Systemd Host**, with
ID=openwrt-systemd, ID_LIKE="openwrt lede" and
VARIANT_ID=native-systemd. Standard procd images keep their existing identity.
The native template is package/base-files/os-release.systemd; release,
revision, architecture and board values still come from the normal build
metadata. OPENWRT_FEATURES lists the capabilities built into the image:
router, plus desktop, virtualization, flatpak and containers when
their corresponding packages are selected.

Agents should read the OPENWRT_* identity fields before choosing administrative
commands: this host uses glibc and matching native APK repositories, systemd
for the default init and process supervision, and UCI/netifd/procd init
scripts for router service configuration. Firmware flashing
requires procd recovery. OPENWRT_DEFAULT_INIT describes the default boot mode;
check /proc/1/comm for the current mode, since recovery runs procd.

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
in UCI. Avoid adding a second native unit for an existing procd service; its
daemon already runs as `openwrt-NAME@INSTANCE.service`.
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
python3 -B scripts/tests/test-network-wait-online.py
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

### Network readiness verified on 2026-10-31

`systemd-openwrt` 13 adds `openwrt-network-wait-online.service`. The host test
(14 cases) drives the helper with the target `jsonfilter` against scripted
netifd dumps: netifd absent or still loading, loopback only, absent devices,
dynamic and manual interfaces, upstream outages, a LAN device that appears after
the upstream links, DHCP-only configuration, explicit and `--any` selections,
timeouts and invalid arguments. Run read-only on the router, the helper selects
`lan`; explicit `--interface lan --interface wan` reports both up.

A disposable KVM/UEFI VM booted the published g42 image
(SHA-256 `2fee3574e9f975e96ba2c522a59f4bb098ba4a5b0476bf71ad26acfb431389f9`)
on a fresh overlay. It carried the router's network configuration, so its PPPoE
WAN never connected. After first-boot kernel adoption completed, a lingering
rootless user received a probe unit with a Quadlet's ordering
(`After=podman-user-wait-network-online.service`) that requires `br-lan` and
runs `pasta -i br-lan`.

| Check | systemd-openwrt 12 | systemd-openwrt 13, two boots |
| --- | --- | --- |
| `network-online.target` reached | 9.2 s, before netifd | 22.9 s and 23.0 s |
| `br-lan` up | 23.7 s | 22.7 s and 22.9 s |
| Wait helper result | not present | `Network is online: lan` |
| Rootless probe | `br-lan` absent; failed | `br-lan` present; pasta started |
| PPPoE WAN down | n/a | did not hold the target |
| `multi-user.target` reached | 31.5 s | 30.2 s and 30.4 s |
| System state | running | running, no failed units |

The version 12 run added `network-online.target` to `multi-user.target` by hand,
reproducing the router, where netdata and other units want the target. Without
any system consumer the target was never activated and Podman's user wait timed
out after 90 seconds. The version 13 APK was installed with
`apk --cache-dir`; the symlinks it ships replaced the manual one. This is VM
validation. The router itself has not been updated, and physical PPPoE timing
was not tested.

Evidence: `bin/validation/sync-20261031/wait-online/` (APK, command scripts,
controller output and serial logs).
