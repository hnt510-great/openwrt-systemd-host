# TUN and native D-Bus readiness repair (2026-10-25)

## Failure evidence

On the physical N5105 router, lingering user managers started at 14:53:32,
TUN was loaded at 14:53:35, and the legacy rootless permission hook ran around
14:53:49. The containers first reported a missing device, then permission
denied, and succeeded after two retries. Neither modules-boot.d nor START=99
orders the legacy ACL hook before native user managers. The original helper
also silently succeeded when the device was absent. Pasta drops supplementary
groups, so enrolled-user UID ACLs are necessary in addition to the device group.

During the previous package migration, the old dbus init script started a
second system daemon under procd with `--system --nofork --nopidfile`.
The native daemon remained running, but new clients reached the replacement
socket. The second daemon lacked systemd activation and invoked the helper
for hostnamed/login1; their `Exec=/bin/false` declarations deliberately require
systemd handoff. Restoring the native bus disconnected persistent consumers,
producing logind's `Transport endpoint is not connected` session failures.
The existing dbus 1.16.2-r9 init guard is already installed on the router.

## Implementation and interfaces

- `openwrt-podman-rootless-5` installs a native preparation oneshot and a
  user@.service drop-in with Wants/After ordering. Preparation loads tun and
  invokes `podman-tun-permissions --require-device`. Ordinary login is not
  made conditional on preparation success. The legacy recovery hook remains.
- Permission updates use flock to serialize ACL and managed-UID ledger updates.
  Unrelated ACL entries are preserved; removed enrolled UIDs are revoked.
- `systemd-openwrt-11` verifies the bus connection reaches its native MainPID
  and that systemd activation is enabled. `openwrt-dbus-ready --check` additionally
  verifies PID 1 owns org.freedesktop.systemd1 and is a read-only live audit.
  PID 1 is deliberately not required during ExecStartPost: it reconnects after
  dbus.service finishes starting, so waiting there creates a readiness cycle.
- This barrier does not promise WAN or DNS availability. Application network
  readiness and unrelated journal warnings remain separate work.

## Source and VM checks

Commands:

```sh
python3 scripts/tests/test-boot-readiness.py
python3 scripts/tests/test-podman-native-storage.py
python3 scripts/tests/test-sshd-systemd.py
make -j12 NO_DEPS=1 CONFIG_OPENWRT_KERNEL_SEQUENCE=30 \
  package/custom/openwrt-podman-rootless/compile \
  package/system/systemd-openwrt/compile V=s
git diff --check
```

The 10 helper/ownership tests, 7 storage tests, and 16 SSH ownership tests
passed. Shell syntax checks and both focused package builds passed; .config
was preserved. An additional C service-bridge regression attempt could not
compile because the existing staging tree lacks libubus.h; no bridge C code
was changed by this repair.

The native systemd guest smoke also passed: service ownership, LAN/ubus,
timers, socket activation, cgroup limits, journald/logread and preservation
listing. Its system-bus assertion now calls the live identity audit.

An isolated QEMU/UEFI VM used the existing Linux 7.3 image, generation 31,
with ABI 5001c59b1072ebdf1a2ed551a854f37a. The physical router runs generation
30 of the same ABI. The image predates the ELF metadata migration, so installing
unrelated dbus-r9 binaries would require its separate dependency migration.
For the ownership regression only, the VM used the exact r9 init-guard script
with its existing dbus libraries. Both newly changed APKs were installed and
tested as signed artifacts, without bypassing dependency checks.

The guest smoke is `scripts/tests/boot-readiness-guest.py`; its
`--inject-legacy` option is restricted to QEMU guests and must never be run
on the physical router. It reconstructs the old duplicate bus command,
confirms hostname fails and the live audit detects the wrong daemon, then
restores the native bus and its test consumers. All six legacy init actions
preserve the original native PID and leave no procd D-Bus instance.

Two ordinary enrolled users had linger and preloaded Alpine 3.23 pasta
containers exposing local HTTP endpoints. Two poweroff/start cycles passed:

| Check | Cold boot 1 | Cold boot 2 |
| --- | --- | --- |
| Preparation completed before either user manager starts | pass | pass |
| Direct UID ACLs for both accounts | pass | pass |
| Both containers active with NRestarts=0 | pass | pass |
| Both HTTP endpoints respond | pass | pass |
| Native bus ownership, hostname and session listing | pass | pass |
| System and test-user failed units | zero | zero |

The VM uses isolated user networking; only its WAN was changed to DHCP and
its inherited proxy disabled. Existing host libvirt guests were untouched.
Container DNS and outbound HTTP were also checked before the cold boots.
A further failure injection replaced only the disposable VM preparation unit
command with `/bin/false`: a fresh ordinary user manager still started, and
both existing HTTP containers kept running. The override was then removed
and the preparation unit recovered successfully.

## Publication and physical deployment

The coordinated publisher staged both signed views and validated the physical
router before promotion. Its changed userspace package set contained exactly
the two packages above; it reused the existing kernel payloads. The signed
userspace snapshot is `20261024T215542.741734Z`.

| APK | SHA-256 |
| --- | --- |
| openwrt-podman-rootless-5.apk | 133fd7eac8d3f3bec80cee0633abc8a51a40d8ae8a05cbcf2d5b1a1a8d201588 |
| systemd-openwrt-11.apk | ca6b059094725212a2f67be3b1920b1a1a58aaf1fdb56f5082143641c9cbe45f |

The router's world uses exact APK checksum constraints. Only these two
existing constraints were refreshed to the new verified identities; all other
world lines and package selections were retained. A signed two-package private
repository, exact offline plan comparison, baseline/config/kernel hashes,
file/database backup, and an independent 20-minute rollback timer protected
installation. It ran in a transient systemd unit at 05:59:22--05:59:31 +08.
Private deployment evidence and backups are under
`/root/boot-readiness-20261025` on the router; no credentials or backups are
included in this repository.

The new preparation unit was started without restarting existing user managers
or workloads. Initial runtime acceptance confirmed unchanged boot ID, tracked
system and user service PIDs, container IDs, ACLs, routes, protected configs,
and normalized firewall rules. Native bus identity, hostname, session listing,
LAN/AriaNg/SearXNG HTTP endpoints, and kernelctl check passed. The package
database delta was exactly the two intended upgrades.

The full runtime observation ran from 06:00:48 to 06:10:54 +08 (606 seconds).
All 13 periodic checks passed, preserving the baseline invariants and reporting
healthy bus/session/HTTP behavior. Final package/kernel verification passed
and the independent rollback timer was then cancelled on acceptance.
The initial deployment did not reboot the router. Physical reboot results are
recorded separately below; the two cold boots above remain VM evidence.


## Physical reboot follow-up (2026-10-25 06:13 +08)

The user rebooted the router. Inspection at 06:15--06:17 found boot ID
`00000000-0000-4000-8000-000000000001`, still running generation 30.

- TUN preparation completed at boot +16.102 s, before user managers began at
  +16.423 s (builder) and +16.441 s (aria2). Both direct UID ACLs were correct.
  There were zero missing/denied TUN device errors in this boot.
- The native system bus and logind started without restart. The live identity
  audit, hostnamed activation, hostname sync, and fresh SSH session registration
  passed. No helper activation failures, disconnected session errors, or procd
  D-Bus instance were found.
- Sunshine, PipeWire and WirePlumber were active with no restart. The GTK portal
  initially raced display startup but recovered; current system and both user
  managers had zero failed units.
- Aria2, AriaNg and SearXNG were running; LuCI, AriaNg and SearXNG HTTP probes
  returned 200. However, each container retried twice before becoming active.

Those retries are a separate LAN readiness race: network-online.target was
already active at boot +12.609 s (06:13:20), while netifd only configured LAN
around 06:13:35. Pasta attempts at 06:13:24 and 06:13:34 could not bind
192.0.2.1 and returned `Cannot assign requested address`; initial DNS was
also unavailable. The user wait-network unit reported success based only on
that prematurely active target. The VM fixtures bound loopback addresses,
so those successful boots did not establish physical LAN address readiness.
Thus physical validation passes the TUN/ACL and bus/session fixes, but does
not pass a zero-retry container startup criterion. Actual LAN/DNS readiness
requires a further change; no service or configuration repair was made during
this inspection.

Other remaining warnings include the previously identified old CPU microcode
and optional desktop components. This boot also logged an ignored ubusd ACL
file: /usr/share/acl.d/luci-base.json is root:root mode 0664 (group writable).
That package permission issue should be investigated separately.
