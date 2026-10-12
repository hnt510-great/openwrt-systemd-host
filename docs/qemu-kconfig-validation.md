# QEMU configuration dependency repair

Validated on 2026-10-13 for the x86_64/glibc native-systemd configuration.

## Change

`QEMU_OPENGL` and `QEMU_VIRGLRENDERER` were inside an `if PACKAGE_qemu-*`
guard. Their conditional Mesa and VirGL dependencies propagate target and
libc prerequisites back to the QEMU packages, closing a Kconfig cycle.
Even a menu `visible if PACKAGE_qemu-*` retains a cycle through VirGL's
selection of OpenGL and its prompt visibility.

Move only those two options into an independent `QEMU graphics configuration`
menu. Retain their `HAVE_MESA` prerequisites, disabled defaults, and
`QEMU_VIRGLRENDERER` selection of `QEMU_OPENGL`. VNC, SPICE, USB, seccomp,
compression, library dependencies and configure flags are unchanged.
The graphics menu is also visible when no QEMU emulator is selected; neither
graphics option defaults to enabled.

## Validation

Regenerate package metadata with `make prepare-tmpinfo -j1 V=s` and the
packages feed index with `./scripts/feeds update -i packages`.
`make defconfig -j1 V=s`, with `KCONFIG_CONFIG` pointing at a temporary output,
exits 0 and reports no QEMU recursion. The original `.config` is unchanged,
and its normalized output retains every existing configuration value.

Full-tree `--fatalrecursive` validation still reports the existing
`luci-app-weechat`/WeeChat provider cycle. For focused strict validation,
generate a temporary package Kconfig using
`scripts/package-metadata.pl --ignore luci-app-weechat config tmp/.packageinfo`
and source it from a temporary copy of `Config.in`. No generated repository
file is edited, and WeeChat source is unchanged.

| Strict configuration case | Result |
| --- | --- |
| Current configuration: QEMU, SPICE, VNC, OpenGL and VirGL enabled | Pass; all existing values retained |
| OpenGL and VirGL disabled | Pass; QEMU, SPICE and VNC remain enabled |
| OpenGL enabled, VirGL disabled | Pass |
| VirGL enabled with OpenGL initially disabled | Pass; VirGL selects OpenGL |

`make package/feeds/packages/qemu/compile -j4 V=s` completes successfully,
also with `KCONFIG_CONFIG` directed at the temporary normalized output.
The build configuration reports SPICE, VNC, OpenGL, GBM and VirGL enabled,
and produces `bin/systemd/packages/x86_64/packages/qemu-x86_64-softmmu-11.1.1-r3.apk`.
The source `.config` and `.config.old` remain byte-for-byte unchanged.

## Feed patch

The repair is applied in the independent packages feed and exported as
`patches/feeds/0005-packages-qemu-kconfig.patch`, based on packages commit
`d02536bfe97a42d31d0f97c0eee8e772bbf200d9`. The packages feed fix is committed
as `a551dd96e41ecfcdae329bafb8c79466abaa45ce`; provenance is recorded in
`configs/qemu-kconfig-feeds.json`. Reverse-application checking passes against
the updated worktree. Apply the patch only to a checkout without this repair.
No changes are pushed.

Logs and configuration fixtures are under
`/tmp/openwrt-qemu-kconfig-fix-9bunp1_h/`. No firmware image build or VM runtime
validation is performed for this configuration repair.
