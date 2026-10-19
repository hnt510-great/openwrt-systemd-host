# Service bridge validation — 2026-10-19

This report describes the earlier proxy-based bridge. For the redesigned scope
and slice implementation, see [cgroup validation](systemd-cgroups-validation.md).

The opt-in service bridge passed package builds, a complete image build, host
tests, and the disposable VM checks below. Subsequent physical deployment is
recorded at the end of this document.

## Accepted image and configuration

Image:

    /srv/openwrt-validation/openwrt-service-bridge-validation-20261019/images/openwrt-x86-64-generic-squashfs-combined-efi.img.gz

SHA-256:

    13bccca4dac2e72388ff08627e9c78fb877b431ccee79b00df40743e701e8bdf

The existing .config was preserved byte-for-byte. Validation used command-line
overrides rather than enabling the feature in the user's configuration:

    make -j4 V=s \
      CONFIG_OPENWRT_SYSTEMD_SERVICE_BRIDGE=y \
      CONFIG_PACKAGE_systemd-openwrt-services=y \
      BIN_DIR=/srv/openwrt-validation/openwrt-service-bridge-validation-20261019/images

Strict conf --fatalrecursive validation passed for temporary configurations
with the feature both disabled and enabled. Unrelated edits, feed heads,
feed working-tree status, and stashes matched their initial snapshots.

## Results

The accepted image was cold-booted with UEFI in an isolated q35/KVM VM with
two vCPUs, 3 GiB RAM, and separate LAN/WAN virtio NICs.

| Check | Result |
| --- | --- |
| Target package and complete image builds | Passed |
| Isolated binary/IPC host tests | 21 passed |
| New C source checkpatch | 0 errors, 0 warnings |
| Original init-script coverage | 53 bridged scripts audited; native D-Bus and recovery-only umount excluded |
| Original actions and custom restart | Passed, including PassWall adapters and exactly-once dispatch |
| Live instance state | Running, partial failure, respawn, permanent failure, and recovery passed |
| Successful process exit | Successful daemon exits remain distinct from failure; sysstat and urandom_seed report completed setup |
| UCI and external init-script actions | Triggers and status synchronization passed |
| Enablement | Shared rc.d settings, enable/disable --now, and reboot persistence passed |
| Authorization | Unprivileged status allowed; unprivileged mutations denied |
| Bridge shutdown/restart | Existing service processes retained; bridge adopted them without restarting them |
| ubusd failure and reconnect | Bridge, procd, and fixture PIDs retained |
| APK transactions | Signed offline verification, simulation, installation, removal, and proxy cleanup passed |
| Router functions | LAN, DHCP lease acquisition in a guest namespace, and DNS passed |
| LuCI | HTTPS returned 200 |
| Native systemd regression | Timers, socket activation, cgroup limits, journald, and logread passed |
| Flashing guards | Valid image check allowed; both shell and ubus flashing rejected under systemd |
| Procd recovery | Bridge absent; original init-script controls passed |
| Failsafe | Bridge absent; persisted overlay accessible |
| Return to systemd | Passed with enabled fixture and boot settings retained |
| Payload identity | Running bridge, rc.common, and systemctl hashes matched image staging |

The VM was powered off after validation. The per-service audit distinguishes
inactive services and nonzero setup-action results; an active aggregate boot
unit does not assert that every optional service or hardware task succeeded.

Build output retained existing kernel tooling/module-description and BIOS
partition-size warnings. Validation used UEFI. Physical NICs, PPPoE service,
hardware watchdog behavior, and physical-device flashing were not validated.
LuCI verification was HTTP-level rather than an interactive browser check.

## Evidence and rerunning

Receipts, the complete build log, runtime payload hashes, service audit,
command results, and VM artifacts are retained in:

    /srv/openwrt-validation/openwrt-service-bridge-validation-20261019/

The accepted receipt is release-pass.json; validation.json records build
arguments and coverage. The earlier development VMs are separate from the
accepted vm-release instance.

Host checks:

    python3 -B scripts/tests/test-systemd-service-bridge.py
    scripts/checkpatch.pl --no-tree --no-signoff --file \
      package/system/systemd-openwrt-services/src/service-bridge.c

Run the guest driver only in a disposable VM. Its normal phase creates an
enabled bridge-smoke fixture for the reboot/recovery phases. The optional
network phase restarts router/proxy services and creates a temporary DHCP
client namespace. The APK phase expects the signed disposable
bridge-apk-smoke fixture package:

    python3 systemd-service-bridge-guest.py --disposable --network --apk /tmp/bridge-apk-smoke-1-r0.apk
    python3 systemd-service-bridge-guest.py --disposable --after-reboot --reconnect
    python3 systemd-service-bridge-guest.py --disposable --recovery

See [service bridge usage and boundaries](systemd-service-bridge.md).

## Physical userspace deployment

On 2026-10-19 the following signed packages were published to the existing LAN
APK feed and installed on 192.0.2.1 after signature verification and an offline
transaction simulation selecting exactly these four packages:

- base-files 1731.3~71194c985d
- libsystemd 262-r5
- systemd 262-r5
- systemd-openwrt-services 1

The scoped incremental publication created snapshot
20261019T070805.660020Z. It retained existing feed packages and changed only the
four packages above; the kernel channel was not changed by this publication.
All four packages were fetched back through the router's configured feeds,
verified with its trusted keys, and matched the installed transaction payloads
byte-for-byte. Installed bridge, rc.common, and systemctl hashes matched the
accepted VM payload hashes.

The bridge is enabled and active. A temporary procd service passed systemctl
enable/start, restart, status, disable/stop, and inactive/disabled checks, then
was removed. Restarting the bridge preserved the existing procd, ubusd, netifd,
dnsmasq, and sshd PIDs. Configuration, original init scripts, SSH configuration,
root authorized keys, account files, and rc.d startup choices were preserved.
The package inventory changed only for the four intended packages. APK retained
locally modified defaults as .apk-new files; these were not applied.

The boot ID and running kernel remained unchanged. No reboot or firmware flash
was performed. Live network, DNS, firewall, and PassWall status reported active;
DNS resolution succeeded and LuCI HTTPS returned 200. Setup tasks that completed
before bridge installation report unknown because no completion was observed;
they were not rerun to manufacture a status result. Completion receipts will be
recorded when their original actions next run, including a future normal boot.

Host publication and deployment receipts are in the validation directory's
deployment/ subdirectory. The router's private configuration backup, transaction
logs, and before/after inventories are under
/root/service-bridge-deploy-20261019/ (root access only).
