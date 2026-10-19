# Scope and slice validation — 2026-10-19

This redesign was first built and tested in disposable QEMU/KVM guests. The
subsequent explicitly authorized publication and physical userspace deployment
are recorded below.
The earlier [proxy bridge report](systemd-service-bridge-validation.md) describes
a different implementation and is not evidence for this redesign.

## Exact image

Accepted image:

    /srv/openwrt-validation/openwrt-cgroup-validation-20261019T154214/images-final/openwrt-x86-64-generic-squashfs-combined-efi.img.gz

SHA-256:

    8ffc3c62eba6e8da170fb5c79f5ab194ff8475d50aa9d9f58c42c523ef1b7382

The immutable decompressed image was booted through a fresh disposable qcow2
overlay, with UEFI, KVM, two vCPUs, 2 GiB RAM, and isolated restricted LAN/WAN
user networks. Runtime systemd was 262; kernel was
`6.18.55-owrt-1e6d3a41204c57acfef0c7a584b7cc0e-r1-g19`.
Guest procd, ujail, registration helper, bridge, rc.common, and rcS hashes
matched the final image staging files. Patched procd sources matched the
prepared sources used for that image.

Build command (the user's `.config` was not edited):

    make -j4 V=s \
      CONFIG_OPENWRT_SYSTEMD_SERVICE_BRIDGE=y \
      CONFIG_PACKAGE_systemd-openwrt-services=y \
      BIN_DIR=/srv/openwrt-validation/openwrt-cgroup-validation-20261019T154214/images-final

## Results

| Check | Result |
| --- | --- |
| Native procd/ujail/bridge and full image build | Passed |
| Bridge binary and IPC host tests | 22 passed |
| Strict Kconfig, bridge disabled and enabled | Passed with temporary configs |
| Procd patch checkpatch | 0 errors/warnings with `--no-tree --no-signoff` |
| Separate non-systemd procd/init/ujail/uxc build | Passed |
| Actual main/worker membership | Original procd child PID and descendants in execution scope |
| Dynamic instance add/remove | Unchanged main PID retained; removed instance stopped |
| Six forced daemon crashes | Original procd respawn policy; old workers drained and scopes collected |
| Non-respawn daemonizing command | Child retained after normal parent exit; explicit replacement/delete drained it |
| Legacy double fork and custom restart | Inherited scope; exactly one original restart; original stop behavior retained |
| Bare non-rc.common script | Bridge and rcS boot placement, original stop passed |
| UCI triggers and CLI authorization | Passed |
| Bridge restart, manager reload/reexec | Existing workload PIDs retained |
| Ordinary registration failure | Logged inherited fallback; no root `services`/`containers` tree |
| Slice resource limits | Fork refusal at TasksMax=8; memory allocation killed at 64 MiB with swap disabled |
| Graceful procd restart and SIGKILL | Enabled fixture restored in fresh scope; old scope collected |
| Independent Podman during procd restart/crash | Container PID retained through both |
| Passwall client and Server | Real SOCKS client → server → controlled HTTP backend traffic passed |
| Passwall monitor and locks | Killed Xray recovered through original monitor; concurrent restarts passed |
| Firewall, dnsmasq and network | Original reload/restart, live nft rules, LAN DHCP lease and DNS passed |
| OCI ujail | Delegated supervisor/payload leaves, real memory/pids controls, bounded paths and full cleanup passed |
| Rootful and rootless Podman | Offline image, subordinate IDs, independent manager cgroups, memory/pids limits and controlled container networking passed; rootful launch from an OpenWrt scope also passed |
| Native systemd regressions | Timer, socket activation, limits, journald and logread passed |
| Reboot enablement | Procd and bridge fixtures resumed with real placement |
| Procd recovery | Original supervision/actions passed with bridge absent |
| Failsafe | Bridge absent; persisted overlay and fixtures accessible |
| Return to native systemd | Procd/bare boot scopes, bridge enablement and OCI/Podman tests passed |

The host/guest tests are in `scripts/tests/test-systemd-service-bridge.py`,
`systemd-cgroup-guest.py`, `systemd-cgroup-services-guest.py`,
`systemd-service-bridge-guest.py`, and `systemd-guest-smoke.sh`. Guest tests
require an explicit disposable flag where supported. Private VM evidence,
image hashes, build logs, source snapshots, preservation audit, and serial
transcripts are retained in the external validation directory above. All test
VMs were stopped; the accepted-image VM completed a native poweroff.

## Boundaries and observations

These tests preserve original init handlers and exercised the installed
Passwall scripts without modifying them. They do not prove every possible
third-party script or physical hardware configuration. Programs bypassing
rc.common, rcS, the bridge runner, and procd inherit their launcher's placement.
No generic PID migration or legacy process reaper is introduced.

A deliberate ubusd crash proved that procd and the bridge reconnected without
restarting the fixture. In that fault-injected guest, rpcd did not restore its
UCI object, which prevented a later Lua UCI consumer from starting. Reboot
restored that prerequisite; the successful traffic/container suite ran after
that reboot. The existing rpcd connection recovery is outside this patch.

The selected kernel lacks CONFIG_NET_VRF, so successful VRF/BPF socket binding
was not runtime-tested. The native VRF path is confined to a delegated payload
and fails closed; a positive VRF test needs a kernel with NET_VRF enabled.

The initial optional signed APK test in the fresh image was blocked by its
kernel-adoption prerequisite. Subsequent upgrade testing used a disposable VM
with the earlier proxy image and completed adoption; its real signed five-package
upgrade and rollback both passed before physical activation. Package builds
and VM runtime tests alone do not constitute publication or physical deployment.
The bridge discovers installed scripts on demand; it has no generator or
persistent proxy units.

`.config` remained byte-for-byte unchanged. Main refs/stashes, all feed
HEADs/status/stashes, and unrelated tracked edits matched the initial snapshot.

## Authorized publication and physical deployment

After the user requested publication and deployment, five signed APKs were
published to the router's existing exact-ABI LAN feed. The scoped incremental
publication created snapshot `20261019T150045.259945Z`, changing only base and
target repositories. No same-version payload was replaced, and the kernel
channel was not changed.

| Package | Deployed version |
| --- | --- |
| base-files | 1731.4~71194c985d |
| procd | 2026.10.07~6a22d396-r4 |
| procd-ujail | 2026.10.07~6a22d396-r4 |
| systemd-openwrt | 9 |
| systemd-openwrt-services | 2 |

The physical router `192.0.2.1` fetched these packages through its configured
feeds. Their hashes matched the frozen VM-tested APKs; trusted signatures and
the exact five-package offline transaction simulation passed. No other package
version changed.

A separate disposable VM tested an upgrade from the previous proxy design and
rollback to the exact original inventory, world constraints, rc.common, and
active services. The initial simple supervisor-restart sequence left the old
rpcd alive. The accepted activation sequence therefore stops original legacy
handlers, stops the original rcS unit, and drains old instances through procd's
API while its event loop is still running. It repeats the drain after package
scripts, then restarts procd and original boot handlers. It never writes to
systemd-owned cgroups or migrates live PIDs. Empty legacy cgroup directories
can remain until reboot; they contain no processes.

The router completed that same sequence under an independent transient native
unit, with original signed packages and a timed rollback available. The timer
was cancelled only after host reconnection and final verification. Passwall
Server resumed after its original configured boot delay; no delay setting was
changed. The rollback path was tested in the VM, not invoked on the router.

Physical checks passed:

- All 23 running procd instances had manager-owned scopes and matching PID
  membership; two Passwall client/helper daemons and one Server daemon occupied
  their service slices. No persistent proxy process remained.
- A temporary isolated fixture proved actual main/worker placement, procd
  respawn into a fresh scope, old-worker cleanup, and scope collection. Restarting
  only the bridge retained its daemon and procd PIDs. The fixture was removed.
- Original LAN, firewall, dnsmasq, and SSH controls were active. Local and external
  DNS, external HTTPS, and LuCI HTTPS (200) passed.
- The three existing rootless containers retained their IDs and PIDs. Rootful
  and rootless container cgroup/resource/networking functionality had already
  passed in the VM; no production container was created for this deployment.
- Accounts, keys, UCI configuration, rc.d choices, GRUB, protected kernel state,
  unrelated world constraints, and the package inventory outside these five
  packages were preserved. rc.common changed intentionally; target package pins
  in world were normalized to allow future upgrades. The only other existing
  file hash change was the clock's `/etc/adjtime`.
- Boot ID and running `...-r1-g18` kernel remained unchanged. No reboot, firmware
  flash, kernel/module/header upgrade, or live cgroup migration occurred.

The deployment receipt and logs are in the external validation directory's
`deployment/` subdirectory. The private remote backup, original signed APKs,
before/after snapshots, and logs are retained with root-only access under:

    /root/cgroup-deploy-20261019/

Physical recovery boot, positive NET_VRF binding, and every possible third-party
script remain outside this deployment's runtime proof. All disposable VMs used
for the migration tests have been stopped.
