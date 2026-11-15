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
build or an installed-r14 APK transaction. Publication and physical-router
installation/reboot are not performed. Real TPM, WAN/LAN hardware, Wi-Fi/rfkill,
backlight, smartcard, printer and complete GNOME/keyring acceptance are separate.

Not covered: physical device acceptance, actual GNOME startup with the new rules,
removable data-disk hotplug, sound replay, and configfs late loading. These remain
promotion checks where the corresponding hardware/function is in use.

The no-TPM client received the rule overlay after boot; a candidate-image
no-TPM cold boot is not established by that result. The r8 suite validates
virtual Ethernet only, not physical NIC/PPPoE/Wi-Fi behavior. No test guests
or swtpm processes from this validation were left running.
