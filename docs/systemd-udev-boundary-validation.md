# Device-management boundary validation — 2026-11-15/16

## Source and package checks

| Check | Result |
| --- | --- |
| `test-systemd-udev-boundary.py` | 3/3 passed, including udev syntax verification and forbidden policy actions |
| `test-procd-units.py` | 9/9 passed |
| `test-gnome-keyring.py` | 1/1 passed |
| `test-desktop-gpu-coldplug.py` | 4/4 passed |
| `make package/system/systemd/compile -j3 V=s` | Passed; generated 262-r14 packages. Existing build dependency warnings were present. |
| Rule payload | Source equals systemd-udev ipkg staging and assembled native-systemd rootfs byte-for-byte |
| `git diff --check` | Passed |

Candidate: `bin/systemd/packages/x86_64/base/systemd-udev-262-r14.apk`, SHA256
`189b924487f864daef6a96fa9d442d4377fc537bae015cf549f822dfd4126e9d`.
Build log: `/tmp/systemd-udev-boundary-build.log`.

## Runtime evidence

Image SHA256: `75131c7b74e0ee3464670aab7938dbd6030f0c0e50e77299e4ba218cff4a38f0`.
Evidence: `build_dir/udev-boundary-validation-20261116-r5/` and
`build_dir/udev-boundary-validation-20261116-r7/` and
`build_dir/udev-boundary-validation-20261116-r8/` (untracked harness, serial and
command logs, JSON receipts). No physical network is bridged into the guests.

| Check | Result |
| --- | --- |
| TPM device notification | RM and raw device units active; tpm2.target active |
| Persisted swtpm cold start | Dummy credential encrypted before power-off and decrypted after a new QEMU start with the same disk/TPM state |
| Spare veth add/remove | Alias device active on add, inactive after deletion |
| Loop attach/detach | Device active with backing file, inactive after detach |
| Delayed TPM reappearance | Actual TPM parent driver unbound/rebound; device became inactive then active and credential decrypted again (r7) |
| Isolated router/client suite | r8 passed all 9 checks: native init, router services, WAN/LAN DHCP, DNS, routing/NAT, LuCI authentication/HTTP and ubus board |
| No-TPM client | Client QEMU has no TPM device; candidate rules loaded, network/management checks completed without a TPM dependency gate |
| FUSE API filesystem | fusectl mounted at the canonical path |
| configfs API filesystem | Skipped: test image has no loaded configfs module; not evidence of late-module support |

The r5 run stopped on an overly strict configfs presence assertion after the
individual successful probes above. Earlier local harness attempts exposed
serial upload/socket and swtpm lifecycle problems, not rule failures. The fixture
uses a 20-second poweroff deadline and fell back to QEMU SIGTERM before the
persisted-state restart; this does not establish clean guest shutdown behavior.
The r7 probe establishes TPM reappearance. Its broad net-unit check used an
unescaped bridge name and stopped before the network suite. The r8 fixture uses
`systemd-escape --path` and passed the remaining isolated router/client checks
(`validation.json`: status=passed, all 9 checks true).
The earlier ACPI-only driver-path assumption was corrected by discovering the
actual TPM parent driver. These fixture failures are retained in their receipts.

This is a targeted rule-overlay test on the existing image, not a new firmware
build or an installed-r14 APK transaction. At the VM stage, publication and physical-router
installation/reboot had not been performed; see the deployment record below. Real TPM, WAN/LAN hardware, Wi-Fi/rfkill,
backlight, smartcard, printer and complete GNOME/keyring acceptance are separate.

Not covered by the VM stage: physical device acceptance, actual GNOME startup with the new rules,
removable data-disk hotplug, sound replay, and configfs late loading. These remain
promotion checks where the corresponding hardware/function is in use.

The no-TPM client received the rule overlay after boot; a candidate-image
no-TPM cold boot is not established by that result. The r8 suite validates
virtual Ethernet only, not physical NIC/PPPoE/Wi-Fi behavior. No test guests
or swtpm processes from this validation were left running.

## Publication and physical installation — 2026-11-16

Source commit: `8a8ca70f09` (`systemd: restore device visibility within OpenWrt
policy boundaries`). The coordinated wrapper dry run and production run both
passed signatures, retained-artifact ABI/dependency checks, immutable identities,
router baseline checks and upgrade simulations. Only the nine systemd-family
262-r14 packages changed; `same_version_rebuilds=[]`. Kernel publication was
unchanged at `7.3.4-64-openwrt`.

Published userspace snapshot:
`/srv/openwrt-feeds/public/snapshots/20261115T162551.003264Z` (UTC timestamp).
Every deployed APK SHA256 matched that immutable snapshot. Evidence is in
`build_dir/udev-boundary-deployment-20261116/`: publication receipts, exact package
manifest, signature/hash checks, offline simulation, install and acceptance logs.

Access used shell SSH to `router-admin@192.0.2.1` with `sudo -n`, not a remote-access
MCP. No UCI setting was changed. An exact offline simulation preceded installation
of the identical nine signed files with repository/network access disabled.
Bare package names were retained in the add transaction, preserving the original
APK world byte-for-byte rather than leaving local-file checksum constraints.

| Physical check | Result |
| --- | --- |
| Installed package set | libsystemd, libudev-systemd, systemd, systemd-udev, coredump, hostnamed, machined, nspawn and oomd upgraded from 262-r13 to 262-r14 |
| APK journal | Transaction completed; `apk-resume --status` reported no interrupted transaction |
| Rule | Target syntax check passed; SHA256 `7f82a9d1dc74347bb234182c40149fbaf6383452212fa438a5b2123de619f657` equals source |
| Activation | Reloaded manager/rules and issued only TPM/net `change` events; no full add replay |
| Device state | dev-tpmrm0.device, dev-tpm0.device and tpm2.target active; current non-lo network aliases active |
| Credential and keyring | TPM decryption matched the existing desktop runtime credential without printing it; login collection Locked=false |
| Routing | LAN and PPPoE WAN up; default route present; local DNS resolution and outbound HTTPS returned successfully |
| Preservation | Boot ID, APK world, network/firewall/DHCP/fstab/desktop configuration hashes, desktop/procd/udevd main PIDs unchanged |
| Running executables | PID 1 and udevd executable hashes equal the installed files; no restart/reexec required for changed executable bytes |
| Health | No failed units; needrestart complete, 203 processes scanned, zero unreadable processes, no warnings or applications/services requiring restart |

The package retained the existing machine-id and generated a conffile
`/etc/machine-id.apk-new`; it was not substituted for the host identity. APK also
warned that interruption recovery might require network inputs; the transaction
completed and no pending journal remained. No service/session restart, firmware
flash, kernel installation or router reboot was performed.

This establishes live TPM/device integration and router-side connectivity after
installation. It does not establish a physical cold boot, a new GNOME session,
real LAN-client forwarding/throughput, removable-disk/sound replay, or configfs
late loading. Existing sessions remained running throughout.
