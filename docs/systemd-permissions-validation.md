# systemd permissions validation — 2026-10-11

The three requested capabilities are implemented and included in a complete
native x86_64/glibc/APK firmware build: fixed system-service delegation through
polkit, PAM/logind login sessions, and systemd user services with a user bus.

## Image and build

Image: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`

SHA256: `48eb505140cd01a4200db78db2fdf89a5c0c55266e01b40be608207450290d08`

Versions: systemd 262-r2, polkit 127-r1, Duktape 2.7.0-r1,
D-Bus 1.16.2-r6, PAM-enabled OpenSSH 10.6_p1-r1 and Wayland 1.26.0-r2.
The integration and desktop packages are systemd-openwrt r2 and
openwrt-desktop r4.

The integration package build, Wayland package build and full `make -j3 V=s`
build completed successfully. Shell syntax checks and main/feed whitespace
checks passed. Existing Kconfig dependency-cycle warnings did not prevent
the complete build. Initial VM findings were repaired in source and the full
image was rebuilt before final acceptance: standard system/user D-Bus socket
activation, polkit's sandbox-safe system bus address, and preservation of the
PAM runtime directory by the Wayland shell profile.

Evidence is saved outside the build tree at
`/srv/openwrt-validation/systemd-permissions-validation-20261011-185810/`.
`firmware-final.img.gz` is a frozen copy of the tested image. Final acceptance
used a new qcow2 overlay under `final-vm/`, not the earlier VM with diagnostic
package replacements. Test accounts, keys, passwords, UCI changes and grants
were created only in the disposable guest overlay.

## Verified behavior

| Capability | Observed result |
| --- | --- |
| Native cold boot | systemd PID 1; logind, polkit, system and user buses active; no failed units |
| Exact delegation | Unprivileged request denied before grant; named user starts/stops the exact service after grant |
| Authorization boundaries | Other user, other service, restart outside the verb list, enable, daemon-reload and transient replacement denied |
| Revocation | Subsequent request from a fresh SSH login denied after revocation |
| Grant helper validation | Invalid verbs/accounts, bare templates, writable or user-owned unit files and transient units rejected |
| Terminal authentication | `systemctl` invoked pkttyagent and successfully authenticated the administrator identity `root` |
| SSH PAM | Password and public-key login worked; logind runtime/session environment supplied |
| Console PAM | Real ttylogin password entry registered an ordinary-user `login`/`tty` session with `/run/user/UID` |
| User services and timer | Real SSH login controlled a personal service and a timer that wrote its expected marker |
| Resource controls | User service cgroup had `memory.max=33554432`, `pids.max=16`, and `cpu.max=25000 100000` |
| Last logout | User manager and runtime directory stopped/vanished after the last ordinary session without lingering |
| Linger | Explicit enable kept the manager/service after logout; disable restored cleanup; marker and enabled service survived reboot |
| libvirt compatibility | virt-manager GUI connected to QEMU/KVM; virsh/libvirt/GI runtime smoke passed; libvirt-admin member allowed and nonmember denied |
| Router/native regressions | ubus, LAN, LuCI listener, native timer/socket activation, cgroup limits, journald and logread smoke passed |
| Persistence/upgrade preparation | Machine ID and grants survived reboot; final image passed `sysupgrade -T`; backup included grants, linger and personal unit files |
| procd recovery | procd PID 1; PAM SSH/console password login and bad-password rejection worked without logind; LAN worked |
| Failsafe | GRUB failsafe entry reached the root ash console with PID 1 `init`, the failsafe marker, and no native systemd manager |

Recovery retains libvirt's existing behavior: its native daemons and guests
are not automatically launched by procd recovery. This task does not add
libvirt polkit authorization. Its existing management group remains powerful.

## Scope and maintenance

A graphical polkit agent and pkexec were outside this validation. There are no preconfigured ordinary users or grants.
Logind's power/lid/idle actions remain disabled; background-process behavior
retains `KillUserProcesses=no`. Lingering is an explicit administrator choice.

Feed-local changes are in `feeds/packages/net/openssh/Makefile`,
`feeds/packages/utils/dbus/Makefile`, and `feeds/video/frameworks/wayland/`.
Preserve those changes when updating feeds, along with the main-tree changes
and active `.config`. Unrelated tracked edits were checked against their
pre-task hashes and existing host libvirt VM states remained unchanged.
The disposable VM returned to native mode after failsafe, reached a clean
power-down, and its QEMU process and forwarded listeners were confirmed gone.
The machine-readable result is `final-vm/acceptance-result.json` in the
evidence directory.

These results establish isolated KVM/UEFI behavior. Physical display/input,
NICs, PPPoE, hardware watchdogs and an actual hardware flash were not tested.
Usage and policy details are in [systemd-permissions.md](systemd-permissions.md).
