# Standalone utilities validation, 2026-10-15

Built and selected standalone replacements in this tree and installed the
signed userspace APKs on `builder@192.0.2.1`. BusyBox remains installed.
BusyBox command links fell from **42 to 16** across /usr/bin and /usr/sbin,
and from **24 to 8** in /usr/bin.

The transaction contained exactly **14 additions and one upgrade**.
It did not install a kernel, kmod, libc, init-system or daemon replacement.
The physical router was not rebooted or flashed.

## Commands and packages

| Commands | Standalone provider |
| --- | --- |
| chvt | kbd-chvt 2.10.0-r1 |
| clear, reset; new tput and tset | ncurses-utils 6.6.20260801-r3 |
| hexdump, setsid, hwclock, logger, taskset | util-linux 2.42.2-r1 subpackages |
| pidof | procps-ng-pidof 4.0.6-r1 |
| nslookup | bind-nslookup 9.20.29-r1 |
| nc | ncat 7.991-r2 |
| time | gnu-time 1.10-r1 |
| traceroute, traceroute6 | traceroute 2.1.6-r1 |
| ifconfig | net-tools-ifconfig 2.10-r2 |
| vi | Existing vim-full |
| netstat | Existing net-tools-netstat, now also preferred in /usr/bin |
| ping6 | Existing iputils-ping |
| Eight iptables command names | Existing xtables-nft-multi, corrected alternatives metadata |

The openwrt-full-utils package manages the additional aliases through APK
alternatives and depends on the replacements. Both .config and
configs/x86-64-systemd-desktop.config select all 14 new packages. The full
configuration differs from the saved starting configuration only in these
14 package selections. Existing profile edits were retained.

The iptables-nft upgrade from 1.8.10-r3 to r4 changes its alternative
metadata. Its relative targets previously fell back to BusyBox, which has
no iptables applet. scripts/merge-usr.py now resolves alternative targets
relative to the command's parent and stores absolute merged-/usr paths.
Eight normalizer tests pass, including the relative-target regression and
idempotence. The installed xtables binary was retained.

VM protocol tests found Ncat exiting immediately when --recv-only used a
single explicit listening address. The feed patch adjusts the descriptor
threshold to account for stdin being absent. Both normal and receive-only
listeners now pass IPv4 and IPv6 transfer tests.

## BusyBox paths retained

In /usr/bin:

ash, sh, crontab, fsync, lock, login, netmsg, resize.

In /usr/sbin:

brctl, crond, ntpd, pivot_root, start-stop-daemon, sulogin, switch_root, udhcpc.

OpenWrt shell extensions, authentication, cron's /etc/crontabs layout and
options, DHCP/NTP callbacks, boot/recovery paths and OpenWrt-specific helpers
retain their existing implementations. brctl and fsync were retained
without introducing untested substitutes. Xterm's resize utility requires
an otherwise unused X toolkit in this tree, so the existing resize remains.

No BusyBox applet was disabled or removed. Scripts needing its exact behavior
can continue to invoke `/bin/busybox APPLET` explicitly. Existing interactive
shells and shell builtins remain as configured.

## Validation

The narrow builds covered util-linux, ncurses, procps-ng, bind, net-tools,
Ncat, GNU time, kbd, traceroute, openwrt-full-utils and iptables. Source hashes
are pinned in the package Makefiles.

The separate packages-feed commits for ssh-copy-id, ifconfig, pidof and the
Ncat listener fix are recorded in
[`configs/cli-utils-feeds.json`](../configs/cli-utils-feeds.json). The combined
source diff is retained in
[`patches/feeds/0011-packages-cli-utils.patch`](../patches/feeds/0011-packages-cli-utils.patch).

The exact 15 signed APKs were installed in an isolated QEMU/KVM VM using the
existing x86_64/glibc native-systemd baseline image. Package removal restored
fallback command providers; offline reinstallation restored the same payloads.
The VM then rebooted and passed the command checks again. All regular payload
hashes match the signed APKs both in the VM and on the physical router.

[The runtime check](../scripts/test-full-utils.sh) covers:

- Command resolution and retained OpenWrt helper links.
- Hexadecimal formatting, GNU time and setsid exit codes, CPU affinity and
  process lookup against the retained implementation for core processes.
- Noninteractive Vim editing, terminal output and utility versions.
- IPv6 ping, IPv4/IPv6 traceroute, DNS and interface/socket inspection.
- Normal and receive-only Ncat listeners with real IPv4/IPv6 loopback transfers.
- Logger delivery to OpenWrt logread and read-only iptables inspection.

The VM returned with systemd PID 1 and active OpenWrt services after reboot.
LAN HTTPS / returned 200; this checks the HTTPS service, not an authenticated
LuCI session. No complete replacement firmware image was built in this task.

Strict Kconfig still reports the pre-existing WeeChat dependency cycle.
The baseline and final strict diagnostics are identical; the new packages do
not introduce an additional cycle.

## Physical preservation and rollback

The router's own trusted keys verified all APKs. Offline simulation showed
only the expected 14 additions and iptables-nft metadata upgrade before the
same transaction was applied.

The before/after preservation snapshots are identical for:

- Boot ID, kernel package inventory, running kernel configuration and TUN vermagic.
- Network, firewall, DHCP, PassWall and desktop configuration.
- Account/group files, password file and subordinate UID/GID mappings.
- libc, systemd, procd, BusyBox, zsh and xtables binary hashes.
- Procd, netifd, cron and NTP PIDs, default route and firewall table names.

Host DNS and LAN HTTPS still pass. The router reports no failed system units.
No router daemon was deliberately restarted, and no clock or firewall rules
were changed. Physical reboot persistence was not tested; the VM reboot
coverage applies to the installed package set.

Protected backup and signed packages are retained on the router under
/root/full-utils-deployment-20261015, including the original APK world,
configuration and command symlinks, plus the previous signed iptables-nft APK.
Installer staging was removed. The disposable VM was powered off; pre-existing
host VMs were untouched.

Private build logs, signatures, payload hashes, rollback/reinstall/reboot
records and physical snapshots are in
[busybox-replacements-20261015](/srv/openwrt-validation/busybox-replacements-20261015).
Unrelated work was preserved. No commit or push was made.
