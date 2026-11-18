# Installer components implementation progress

Date: 2026-11-16. This is a partial implementation record, not component ISO acceptance.

The independent installer fixes from section 5 of installer-components-plan.md are
implemented: preserve firewall/port/WAN inputs on return, keep LAN number errors on
the LAN page, reject static WAN network/broadcast addresses and overlapping LAN/WAN
subnets, preserve the original installation error when unmount cleanup also fails,
include disk model/capacity/available serial in confirmation, and use installation
media wording with the LAN management address on completion. The installer package
release increases from 3 to 4. Existing passwords are retained on revisiting PPPoE.

Validation: test-openwrt-installer.py ran 12 tests, 11 passed and one skipped because
host UCI is absent. The UCI matrix's actual-UCI branches also did not execute.
test-installer-optical.py ran two tests, one passed and one skipped for missing
prepared target root/config. git diff --check passed. An injected boot-copy plus unmount failure verifies
that the reported exception retains the installation failure and cleanup detail.

The installer package compile was attempted, but triggered broad dependency
rebuilds and was interrupted (exit 130). Package build acceptance remains pending;
build outputs may have been updated. No package build success is claimed.

These changes do not implement the component rootfs assembler, offline signed
repository, component selection UI, package dependency split, or component-aware
firstboot. No component APK/ISO, VM boot, rolling upgrade, physical device install,
feed publication or reboot is claimed. The main component plan remains pending.
