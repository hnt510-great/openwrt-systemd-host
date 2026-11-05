# Plan: refuse direct `systemctl` control of procd-supervised OpenWrt service instances

Status: implemented and feature-validated in a disposable VM on 2026-11-05.
The block below replaces the earlier "allow and reconcile" approach. See
[the native supervision validation](systemd-native-supervision-validation.md#external-instance-control-guard-2026-11-05)
and [the bridge validation](systemd-service-bridge-validation.md#external-instance-control-guard-2026-11-05)
for the exact image, checks and the observed procd restart-stop timeout.

## Context

In units mode, procd runs every service instance as a transient unit `openwrt-SERVICE@INSTANCE.service`
(`package/system/procd/patches/130-systemd-transient-units.patch`). When someone runs
`systemctl stop|restart|start` on such a unit (e.g. `openwrt-network@instance1.service`, i.e. netifd),
the action goes straight to systemd:

- **stop**: the daemon stops and `Restart=` does not fire. procd only sees "not running", so it can't
  tell this from a normal exit. The bridge status even reports it as "activating; respawn pending".
  The transient unit is garbage-collected, so a later `systemctl start` fails with "Unit not found".
- **restart**: works, but procd sees no stop/start (deactivating and activating both count as
  running) and only picks up the new MainPID.
- Init-script hooks (`stop_service`, e.g. `ifdown -a`) never run.

Decisions made with the user (revised):

- **Refuse** a direct start, stop, restart or reload of a single instance unit. The check is in
  systemd PID 1, so it applies to every client (systemctl, busctl, Cockpit, varlink). Only procd
  itself may request jobs on these units.
- The refusal message names the command that runs the init script:
  `systemctl <verb> openwrt@SERVICE` (service bridge) or `/etc/init.d/SERVICE <verb>`.
- The **service bridge becomes default-on**, so `openwrt@SERVICE` is always available.
- **Slices stay an escape hatch.** `systemctl stop openwrt-SERVICE.slice` is not blocked; it is
  documented as the deliberate whole-service override (for example when procd is wedged).
  `systemctl kill` and stopping `openwrt-procd.service` also keep their current behavior.
- No `RefuseManualStart`/`RefuseManualStop` on the units (procd must still be able to start and stop
  them), no procd change, and no change to the cgroup layout.

Superseded parts of the earlier plan, listed so they are not revived: procd detection of unit
changes made outside procd (old part A: patch 140, `unit_foreign_job`, `unit_external_stop`,
`external_stop` in `instance_dump()`, per-instance `spawn`); the systemctl notices for instance
units and the `start` redirect to the bridge (old B.1–B.3); the bridge `revive` request and the
`external_stop` status state (old C.2, C.4).

## Design

### A. systemd core: refuse foreign jobs on procd instance units

New quilt patch `package/system/systemd/patches/002-openwrt-procd-instance-jobs.patch` on systemd
262, written with `make package/system/systemd/{clean,prepare} QUILT=1` and then
`make package/system/systemd/refresh`. systemd `PKG_RELEASE` goes 11 → 12. Edit only through quilt.
The unpacked tarball carries upstream systemd agent instructions (AGENTS.md/CLAUDE.md) that ask for a
`README.md` edit; that rule is for upstream systemd, and nothing outside this feature may enter the
patch.

1. **Recognise procd instances.** A new `unit_is_openwrt_procd_instance(Unit *u)` in
   `src/core/unit.c` (declared in `unit.h`) matches a unit that:
   - is `UNIT_SERVICE`, passes `unit_name_is_valid(u->id, UNIT_NAME_INSTANCE)` and starts with
     `openwrt-`, and
   - is either `u->transient` (made by procd's `StartTransientUnit`), or has
     `load_state == UNIT_NOT_FOUND` and an executable `/etc/init.d/SERVICE` (an instance that procd
     stopped or never started).

   Units loaded from files never match. Examples are the `openwrt-console@.service` template and
   the guest-test units from `/run/systemd/system/openwrt-smoke@.service`. To get SERVICE and
   INSTANCE, split the name at `openwrt-`, `@` and `.service`, then undo procd's `\xNN` escaping
   (`unit_escape()` in patch 130) with `cunescape()`.
2. **Only procd may request jobs.** A job on a matching unit is allowed only when the requester's
   PidRef equals the main PID of `openwrt-procd.service`. That process is
   `procd --systemd=units`, which talks to PID 1 over `/run/systemd/private`. Every other requester
   is refused, including other processes in procd's cgroup such as hotplug handlers.
   - The requester's identity is looked up only for matching units, so other units cost nothing
     extra.
   - If the identity can't be resolved, the job is refused (fail closed).
   - The rule covers every job type: start, stop, restart, try-restart, reload and reload-or-*.

   Only jobs that a client requests directly are checked. Jobs that follow from dependencies pass:
   BindsTo when `openwrt-procd.service` stops or restarts, a slice stop, isolate and shutdown.
3. **Hook points.** These are all the IPC job entry points. The check runs right after
   `unit_queue_job_check_and_mangle_type()` (`src/core/unit.c` ~7179), so it sees the final job type.
   - `bus_unit_queue_job_one()` (`src/core/dbus-unit.c` ~1981), using `bus_query_sender_pidref()`.
     This covers Manager `Start/Stop/Restart/TryRestart/Reload*Unit`, the single-unit
     `EnqueueUnitJob`, `Unit.Start/Stop/…`, `StartTransientUnit` and D-Bus `EnqueueMarkedJobs`.
   - `manager_add_jobs()` (`src/core/manager.c` ~2311, per-unit loop ~2370). It is reached from the
     multi-unit `EnqueueUnitJobMany(as…)` (`method_enqueue_unit_job_many`, `src/core/dbus-manager.c`
     ~850/903), which systemctl uses for single-transaction starts. Pass the sender message through
     so the loop can look up the requester.
   - `varlink_unit_queue_job_one()` (`src/core/varlink-unit.c` ~575), using
     `varlink_get_peer_pidref()`. This covers `io.systemd.Unit.StartTransient` and
     `io.systemd.Manager.EnqueueMarkedJobs`.
4. **Refusal message.** Return `BUS_ERROR_ONLY_BY_DEPENDENCY`. systemctl maps it to exit status 4,
   `EXIT_NOPERMISSION` (`src/systemctl/systemctl-util.c` ~101), and varlink passes it on through
   `varlink_reply_bus_error`. The existing varlink error has no payload, so patch 002
   adds a nullable `message` field to `OnlyByDependency` and forwards the bus error text.
   The message is one line. Its verb comes from the job type:
   restart-like types become `restart` and reload types become `reload`.

   ```
   openwrt-network@instance1.service is procd instance 'instance1' of OpenWrt service 'network'; a direct stop would skip /etc/init.d/network. Use 'systemctl stop openwrt@network' or '/etc/init.d/network stop'.
   ```

   For a name that isn't loaded:

   ```
   openwrt-network@instance1.service is not running; procd creates the instances of OpenWrt service 'network'. Use 'systemctl start openwrt@network' or '/etc/init.d/network start'.
   ```

   Mention the `systemctl … openwrt@` command only when `/usr/libexec/openwrt-service-bridge` is
   executable, the same test patch 001 uses. Also log one info line on the unit naming the
   requester's PID and comm, so the journal shows who tried.
5. **Report it.** `unit_can_start_refuse_manual()` and `unit_can_stop_refuse_manual()`
   (`src/core/unit.c` ~6513) return false for matching units, so `CanStart` and `CanStop` read `no`
   for clients that check them. `RefuseManualStart` and `RefuseManualStop` stay `no`: procd needs
   its own `StartTransientUnit` and `StopUnit` to work, and the stock flags can't make an exception
   for one caller.
6. **systemctl output.** In `src/systemctl/systemctl-start-unit.c` (~182), leave out the trailing
   "See system logs and 'systemctl status …' for details." line for `BUS_ERROR_ONLY_BY_DEPENDENCY`,
   since the refusal already says what to do. This goes in patch 002 with the rest of the feature.
7. **Not blocked.** These are documented rather than refused:
   - `systemctl kill` and `procd_send_signal` only deliver a signal, and the unit's `Restart=`
     applies as for a crash, so it counts as a respawn. Under `respawn_policy`
     (`Restart=on-failure`), a SIGTERM exit counts as clean and is not restarted, just as when the
     daemon exits on its own.
   - `set-property`, `reset-failed`, `clean`, `freeze` and `thaw`.
   - `systemctl stop openwrt-SERVICE.slice`: the whole-service override. It skips the init-script
     hooks.
   - Stopping or restarting `openwrt-procd.service`, isolate and shutdown, which are dependency jobs.
   - Fallback `openwrt-<id>.scope` children (vrf, trace, bundle, passed descriptors). procd
     supervises these itself, so stopping the scope looks like a crash to procd and follows its
     respawn rules.
8. **Upgrade safety.** All of this is in PID 1, and procd is identified by its cgroup main PID, so
   any mix of old and new procd and systemd works. The block takes effect after a reboot or
   `systemctl daemon-reexec`. procd needs no change.

### B. systemctl CLI (`package/system/systemd/patches/001-openwrt-service-controls.patch`)

This is carried over from the earlier plan. The existing `openwrt@NAME` handling stays as it is.

**Hint for plain names.** For a mutating verb on a bare name that doesn't exist as a unit
(`systemctl restart netifd`), run `openwrt-service-bridge systemctl hint NAME`. It prints, for
example, `netifd is supervised by OpenWrt service 'network': systemctl restart openwrt@network`.
The native command then still runs and fails as before. There is no automatic redirect. Change it
with quilt and refresh it; it shares the systemd `PKG_RELEASE` bump with A.

### C. Service bridge (`package/system/systemd-openwrt-services/src/service-bridge.c`, `PKG_RELEASE` 5 → 6)

1. **Default on**: in `config/Config-build.in`, `OPENWRT_SYSTEMD_SERVICE_BRIDGE` gets `default y`.
   Merge `CONFIG_OPENWRT_SYSTEMD_SERVICE_BRIDGE=y` into the working `.config` with
   `scripts/kconfig.pl + .config <fragment>` + `make defconfig`, without overwriting it. Update
   `configs/x86-64-systemd-desktop.config`.
2. **`hint`**: find NAME as `/etc/init.d/NAME`, or as the basename of an instance's procd
   `command[0]` (netifd → network), using the existing `service list` `ubus_invoke` path. It is
   read-only and prints nothing when nothing matches.
3. Bridge actions need no other change. Init scripts reach procd over ubus, and procd's own
   `StopUnit` calls are allowed.
4. VM regression found that units-mode procd retains `respawn` configuration after a terminal
   systemd crash-loop failure. Prefer an explicit `systemd_state=failed` over the configured
   respawn hint in bridge health; after unit collection removes that state, use the
   completed instance exit code rather than treating respawn configuration as a pending job.
   Cover both cases and a real pending restart in host tests; this is not an `external_stop`
   state or a change to lifecycle actions.

### D. Docs

- `docs/systemd-native-supervision.md`: replace the "bypasses procd's view" paragraph (lines
  38–41) with a short table showing what happens for each action, with netifd as the example:
  - start, stop, restart and reload are refused, with the message;
  - `kill` is a respawn;
  - stopping the slice is the override;
  - restarting `openwrt-procd.service` recreates the instances;
  - `CanStart` and `CanStop` read `no`.
- `docs/systemd-service-bridge.md`: default on, the path that refusal messages suggest, and `hint`.
- `package/base-files/system-description.systemd.md` (~line 79, "optional bridge") and the bridge
  line in `CLAUDE.md` (line 110: "off by default"). Check whether `GEMINI.md` has a matching line.
- After the VM run, add new rows to `docs/systemd-native-supervision-validation.md` and
  `docs/systemd-service-bridge-validation.md`. These are hand-written, with image SHA256, a
  `| Check | Result |` table, a scope statement and an evidence directory outside the repo.

## Verification

1. Builds: `make package/system/systemd/compile V=s` and
   `make package/system/systemd-openwrt-services/compile V=s`. After `{clean,prepare} QUILT=1` and
   `refresh`, patch 002 must apply with zero fuzz and leave no diff.
2. Static checks: `git diff --check`.
3. Host tests:
   - `python3 -B scripts/tests/test-systemd-service-bridge.py`, with new `hint` cases: an init-script
     name, a `command[0]` basename, and no match.
   - `python3 -B scripts/tests/test-procd-units.py`: assert that patch 002 is in the systemd series
     and that systemd's `PKG_RELEASE` went up.
4. Guest test in a disposable VM booted from the exact image (`scripts/tests/procd-units-guest.sh`,
   using `unitprobe`):
   - `systemctl stop|restart|start|reload $unit`: exit 4, and the message names
     `/etc/init.d/unitprobe`. MainPID and NRestarts are unchanged, ubus still shows the instance
     running, and the journal has the refusal line.
   - The same refusal for:
     - `busctl call … Manager StopUnit`;
     - a multi-unit `EnqueueUnitJobMany`;
     - `systemctl set-property $unit Markers=needs-restart` followed by
       `systemctl reload-or-restart --marked`. That one logs a warning and leaves other marked units
       alone.
   - `systemctl show -P CanStop $unit` prints `no`.
   - `/etc/init.d/unitprobe restart` gives a new MainPID. After `/etc/init.d/unitprobe stop`, the
     unit is gone, and `systemctl start $unit` gets the "not running" message.
     `/etc/init.d/unitprobe start` brings it back.
   - `systemctl kill -s KILL $unit` is counted as a respawn.
   - `systemctl stop openwrt-unitprobe.slice` is allowed, as the documented override.
   - The existing `systemctl restart openwrt-procd.service` step still recreates the instances.
     `scripts/tests/systemd-guest-smoke.sh` still stops its file-backed `openwrt-smoke@*.service`
     units.
   - `systemctl restart netifd` prints the hint.
   - Add bridge `start`, `stop` and `hint` checks to `scripts/tests/systemd-service-bridge-guest.py`.
5. Full image through `python3 scripts/build-and-publish.py build-only -j12 V=s`. This reserves a
   generation without publishing. No publication or router deployment without explicit authorization.
