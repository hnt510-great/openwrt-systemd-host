# Distrobox validation, 2026-10-15

Distrobox was added to the x86_64/glibc native-systemd profile, validated from
a clean firmware boot in QEMU, and installed on `192.0.2.1` without rebooting
or flashing the router. All container tests ran as the existing `desktop-user` user
(UID 32769, GID 32770) with rootless Podman 5.8.4 and crun 1.28.

| Installed package | Version |
| --- | --- |
| distrobox | 1.8.2.5-r1, noarch |
| glibc-getent | 2.43_p1-r5 |
| rev | 2.42.2-r1 |

`getent` supplies account/environment lookups through the matching target
glibc. The VM caught an additional dependency on `rev` in `distrobox-enter`;
the package now declares it. No upstream Distrobox source patches are needed.

## Build and exact-image acceptance

The narrow package builds and final `make -j4 V=s` completed successfully.
Both `.config` and the tracked desktop profile changed only the Distrobox,
glibc-getent and rev selections. Kernel configuration, kernel-package
selections, target and init-system settings are unchanged.

Tested image:
`bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`

SHA256:
`88c8f0b6221789c13f941847ca255e944b606e02520239ff3cbfdd976aed848a`

The clean-booted image contains all three package versions. All 70 files from
the signed APK payloads match its root filesystem; published artifact checksums
also pass. Kernel version remains `6.18.55`, with OpenWrt ABI hash
`f10b60a7da5b97b579b974213f7b729c`.

The disposable VM alone received DHCP/DNS settings appropriate to QEMU and a
Pixman desktop renderer. Those adaptations did not alter the source overlay
or physical-router configuration.

## Runtime results

Both systems used the same official Debian 13 image digest:
`docker.io/library/debian@sha256:913f6706df59a68922d1dd08f78c2476560a8d367897200a6005b00e5f67c2d5`.

| Check | QEMU | Physical router |
| --- | --- | --- |
| Create, list, enter, stop, restart and remove | Passed | Passed |
| UID/GID, custom home, shared files and ownership | Passed | Passed |
| Missing HOME/SHELL environment fallback through getent | Passed | Passed |
| DNS, HTTPS and guest apt package installation | Passed | Passed |
| Host command through distrobox-host-exec | Passed | Passed |
| Exported jq command, literal arguments and exit status | Passed | Passed |
| Exported GTK launcher under Wayland and Xwayland | Passed | Passed |
| Actual keyboard input and button activation on both backends | Passed | Passed |
| Container state, packages and GUI after reboot | Passed | Not rebooted |

The GTK fixture was compiled inside Debian against its own GTK libraries.
Backend logs identify `GdkWaylandDisplay` and `GdkX11Display`; actual desktop
input produced the expected marker twice through entry and button activation.

QEMU evidence includes full display captures. Physical PNGs capture the GTK
application's rendering after actual desktop input:
[Wayland](/srv/openwrt-validation/distrobox-validation-20261015/physical-wayland.png),
[Xwayland](/srv/openwrt-validation/distrobox-validation-20261015/physical-x11.png).
The stock Weston screenshooter stalled while collecting capture data from the
existing mirrored outputs. Only that test client was terminated; the compositor
was retained. An optional AT-SPI service warning did not prevent the tested GUI
behavior.

## Physical deployment and preservation

The router's existing trusted keys verified all three APKs. Offline simulation
and installation contained exactly three additions, with no upgrades, removals,
kernel/kmod transactions, or libc replacement. Every installed payload hash
matches the signed, locally tested APKs.

The final snapshot exactly matches the pre-install snapshot for boot ID,
kernel-package inventory, kernel configuration, TUN vermagic, default route,
firewall tables, and core service state/PIDs. Procd PID 1235, netifd PID 3123,
and Weston PID 19639 remained running. Network/firewall/DHCP/PassWall/desktop
configuration, passwd/group, subordinate mappings, and libc/systemd/procd binary
hashes are unchanged. Host DNS and HTTPS still pass.

Test containers, exported launchers/icons, temporary homes and installer staging
were removed. The Debian image remains cached. The three installed packages
remain available. Pre-install configuration/world and signed APKs are retained
under `/root/distrobox-deployment-20261015` for an APK-based rollback.

The validation VMs were powered off. Physical reboot persistence remains
unexercised, as requested. No physical firmware flash was performed.

Strict Kconfig `--fatalrecursive` still reports the existing WeeChat dependency
cycle; its diagnostic is identical on the baseline and final configuration.
The complete firmware build passes. Unrelated work was preserved; no commit or
push was made.

Build logs, package/payload checksums, before/after snapshots, VM reboot records,
test harnesses and captures are retained privately under
[`distrobox-validation-20261015`](/srv/openwrt-validation/distrobox-validation-20261015).
