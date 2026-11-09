# Scheduled maintenance modernization validation

Validation uses temporary repositories and signed APK fixtures. Production
scheduling remains disabled in configuration; no cron entry is installed.
No upstream integration, firmware build or production publication was run.

The scheduler suite covers preservation, exact-image gates, disabled scheduling,
read-only status, package y/m selection protection and manifest receipt binding.
The build/publication suite additionally checks independent saved image copies
and rejection of modified artifact bytes. Existing updater and upgrade-preflight
suites are run as regression checks.

A standalone two-VM check uses a copied existing completed image, independent of
the scheduled runner. This validates virtual routing and LuCI, not physical NICs,
PPPoE, desktop capture, RDP audio or device deployment. Results are recorded below
once the check completes.

## Host results

On 2026-11-09, 218 focused tests passed: 24 scheduler, 65 build/publication,
47 custom updater, 20 mainline kernel updater, 36 upgrade preflight and 26 LAN
publisher tests. Python compilation and `git diff --check` also passed.
The signed fixture suite exercised publication directly from saved artifacts.

The working `.config`, staged diff, original stash list and pre-existing
`GEMINI.md` diff match the private pre-implementation snapshot at
`/srv/openwrt-validation/implementation-backups/20261109T022246`.
Existing untracked files and nested Argon content remain in place. All feature
changes are left uncommitted for review. `--status` reports `enabled: false`.

## Standalone VM result

The copied existing image passed all nine network/management checks under
KVM/UEFI: native init, router services, WAN DHCP, LAN DHCP, DNS, routing/NAT,
LuCI authentication/RPC, LuCI HTTP and ubus board data. Guest kernel:
`7.3.3-56-openwrt`. Image SHA-256:
`42b3d7a88ecda5268023810b8a5282f8dbdc31bef525a5da96a869fdaf523a08`.

Receipt and serial logs: `/srv/openwrt-validation/scheduler-implementation-vm-jojwc3us/vm/validation.json`.
Both guests stopped and disposable raw/qcow2/NVRAM disks were removed by the
harness. No live scheduler run, new firmware build, feed publication or physical
device acceptance is implied.
