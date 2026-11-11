# RealtimeKit and desktop preemption validation

Implements [the RealtimeKit and preemption plan](rtkit-preemption-plan.md);
the user-facing description is in the [GNOME desktop guide](gnome-desktop.md).
Work is split into two phases: userspace (`rtkit`, desktop KMS scheduling)
and the desktop kernel configuration, which needs a new reserved kernel
generation.

Scope: host checks recorded on 2026-11-11, followed the same day by the
user's upgrade of the physical router `192.0.2.1` to kernel generation 59
and the packages below (the upgrade itself was performed by the user). No VM
was booted and no image was flashed. Phase 1 and phase 2 were deployed
together, so no separate `rt_group_sched=0` phase 1 boot or routing-latency
baseline exists.

## Sources and artifacts

| Input / artifact | SHA256 |
| --- | --- |
| `rtkit-v0.14.tar.gz` (`gitlab.freedesktop.org/pipewire/rtkit`, tag `v0.14`) | `55dd379b11f52b81655e2dc676de9d602d050cb0beb18ef01f0f65569f0a5e59` |
| `bin/systemd/packages/x86_64/base/rtkit-0.14-r1.apk` (unpublished host build) | `0c25b4f2156a3f570fa4ff6ee3c5a0383f8d32cecd31fa5f844d360cf9f0a497` |

## Phase 1: userspace, host checks

| Check | Result |
| --- | --- |
| `update-custom-packages.py --check --package rtkit` | `current 0.14 -> 0.14` (GitLab tag catalog) |
| `scripts/tests/test-custom-package-updates.py` | 47 tests pass |
| `scripts/tests/test-rtkit-desktop.py` | 12 tests pass (recipe, polkit rule, UID 193 unique, init/session simulations, kernel baseline) |
| `test-sunshine-gnome.py`, `test-desktop-audio.py` | Pass with the changed `desktop-session` |
| `make package/custom/rtkit/compile V=s` | Builds; payload holds `rtkit-daemon`, `rtkitctl`, D-Bus service/policy/interface, polkit action and `20-openwrt-rtkit.rules`, the unit and `rtkit-daemon.service.d/openwrt.conf` |
| `openwrt-desktop` / `openwrt-desktop-audio` / `base-files` compile | Build `openwrt-desktop-27.apk` (`f7a0219e…f8b5c6`), `openwrt-desktop-audio-1-r4.apk` (`29443fc1…320`) and `base-files-1755.10~89e69d9391.apk`; the staged `system-description.md` describes RealtimeKit |
| `scripts/deptest.sh rtkit` | Not completed: the isolated deptest bootstrap fails in `tools/libdeflate` (no `gzip`/`mkhash` in `tmp/deptest/staging_dir/host`), before any package is tested; unrelated to this change |
| `rtkit.elf.json` | `rtkit-daemon` needs `libc`, `libcap`, `libdbus-1`, `libsystemd`; `rtkitctl` needs `libc`, `libdbus-1` |
| Upstream unit / D-Bus activation | `Type=dbus`, `BusName=org.freedesktop.RealtimeKit1`, `SystemdService=rtkit-daemon.service` |
| `git diff --check` | Clean |

## Phase 2: kernel configuration, host checks

The effective kernel configuration was reproduced outside `build_dir`: the
generic, x86 and x86/64 `config-7.3` files merged with `scripts/kconfig.pl`,
the top-level `CONFIG_KERNEL_*` lines appended as `include/kernel-defaults.mk`
does, then `make olddefconfig` against a clean Linux 7.3.3 tree.

| Check | Desktop `.config` | Stock `.config` (no fragment) |
| --- | --- | --- |
| `PREEMPT` / `PREEMPT_LAZY` | `PREEMPT=y`, `PREEMPT_LAZY` unset | `PREEMPT` unset, `PREEMPT_LAZY=y` (unchanged) |
| `PREEMPT_DYNAMIC` | `y` | `y` |
| `HZ` | `1000` | `1000` |
| `RT_GROUP_SCHED` / `_DEFAULT_DISABLED` | `y` / `y` | `y` / `n` after `make defconfig` writes the new symbol's `default n` |
| `UCLAMP_TASK` | unset | unset |
| §4.2 `awk` filter on `.config` | `# CONFIG_PREEMPT_NONE is not set`, `# CONFIG_PREEMPT_VOLUNTARY is not set`, `CONFIG_PREEMPT=y`, `CONFIG_RT_GROUP_SCHED=y`, `CONFIG_RT_GROUP_SCHED_DEFAULT_DISABLED=y` | — |
| `test-mainline-kernel-updates.py` | Pass | — |

`HZ=1000` and `PREEMPT_DYNAMIC` live in the target configuration and so also
apply to stock x86_64 builds; the preemption model and RT group default follow
the top-level configuration.

## Physical router, kernel generation 59

Read-only checks on 2026-11-11, seven minutes after boot, from
`sudo journalctl -b`, `ps -eLo pid,tid,user,cls,rtprio,ni,comm` and
`/proc/config.gz`.

| Check | Result |
| --- | --- |
| Running kernel | `7.3.3-59-openwrt`, `SMP PREEMPT_DYNAMIC`; command line has no `rt_group_sched=` or `preempt=` |
| `/proc/config.gz` | `PREEMPT=y`, `PREEMPT_DYNAMIC=y`, `HZ=1000`, `RT_GROUP_SCHED=y`, `RT_GROUP_SCHED_DEFAULT_DISABLED=y` |
| Boot log / `sched/preempt` | `Dynamic Preempt: full`; `(full) lazy` |
| Installed packages | `rtkit-0.14-r1`, `openwrt-desktop-27`, `openwrt-desktop-audio-1-r4`, `base-files-1755.10~89e69d9391` |
| `rtkit-daemon.service` | D-Bus activated by `pipewire-pulse` at 18.9 s; active, in `system.slice` |
| rtkit watchdog thread | `RR` 99 |
| `pipewire`, `wireplumber`, `pipewire-pulse` main threads | `TS`, nice -11 |
| Four `data-loop.0` threads | `RR` 20 |
| gnome-shell `KMS thread` | `TS`, nice -15; `Thread 'KMS thread' will be using high priority scheduling` |
| `Failed to make thread`, rtkit denials, `Not authorized` | None in this boot |
| `systemctl --failed` | None |
| `kernelctl list` / `check` | 59 running, default, known-good; 56 fallback; check passes |
| Links | WAN `pppoe-wan`, `br-lan`, WireGuard and `dae0` up |

The upgraded router kept its existing `/etc/config/desktop`, which lacked
`kms_scheduling` (the scripts default to `high-priority`). The option was then
added through `uci-history` (revision 13) with no session restart; gnome-shell
kept its PID and the KMS thread stayed at nice -15.

## Open runtime checks

- `kms_scheduling='realtime'` (`KMS thread` `RR` 20) and `'normal'` have not
  been exercised on the router.
- Routing latency under `preempt=full` and `HZ=1000` has not been measured;
  without a phase 1 baseline, compare against a `preempt=lazy` boot of the
  same kernel.
- `scripts/tests/gnome-desktop-guest.py` has not been run in a guest.
