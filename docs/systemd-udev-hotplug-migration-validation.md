# udev takeover & OpenWrt hotplug compatibility migration validation — 2026-11-25

## 1. Scope & Baseline Inventory (Batch 1)

Base image tested (unmodified desktop baseline):
- Path: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`
- SHA256: `62472686e7d6d3d293594e6470e890362d8cd0e04c4278c61115c44f4e8faa6e`
- Main tree base commit: `8f87d6af5af9` (`origin/main`: `ce51f2ff0f34`)
- `feeds/packages` base commit: `c983b8adf7bf` (`origin/master`: `ea11c8e94b57`)
- Evidence directory: `build_dir/udev-migration-validation-20261125/` (`baseline/baseline-results.json`, `candidate/candidate-results.json`, `extra-checks/extra-results.json`, `pure-router/pure-router-results.json`, `desktop-sessions/desktop-sessions-results.json`, serial logs, command logs)

### Object — Writer — Trigger Order Inventory (Before vs After)

| Managed object | Writers before migration | Writers after migration (single writer) | Trigger / serialization |
| --- | --- | --- | --- |
| `/dev/dri/renderD*` mode/group | `50-udev-default.rules` (`render:0666`) → `etc/hotplug.d/drm/zz-libvirt-render` (`root:render 0660`) → `libvirt-openwrt-prepare` (`root:render 0660`) | `50-udev-default.rules` (default `0666`), overridden in udev by `libvirt-daemon`'s `65-libvirt-devices.rules` (`root:render 0660`) | udev rule evaluation only; `libvirt-daemon` `postinst`/`postrm` reloads rules and issues targeted `--action=add` on `drm/renderD*` only |
| `/dev/kvm` mode/group | `50-udev-default.rules` (`kvm:0666`, `static_node=kvm`) → `libvirt-openwrt-prepare` (`root:kvm 0660`) | `50-udev-default.rules` (default `0666`), overridden in udev by `libvirt-daemon`'s `65-libvirt-devices.rules` (`root:kvm 0660`, `static_node=kvm`) | udev rule evaluation (both static node and live uevent); `libvirt-daemon` `postinst`/`postrm` reloads rules and issues targeted `--action=add` on `misc/kvm` only |
| `/dev/virtio-ports/<name>` symlink | `50-udev-default.rules` (`SYMLINK+="virtio-ports/$attr{name}"`) + `virtio-console-helper` `00-virtio-ports` (`ln -s`) | `50-udev-default.rules` only on native systemd (`00-virtio-ports` omitted when `CONFIG_OPENWRT_SYSTEMD=y`; non-systemd branch unchanged) | udev add/remove lifecycle; `/etc/hotplug.d/virtio-ports` retained for `qemu-ga` (`10-qemu-ga`) and third-party hooks |
| Desktop DRM auto-start & `manual-stop` | Unlocked check in `drm/95-desktop` → `/etc/init.d/desktop start` (unconditionally clears `manual-stop`) vs `desktop.init stop` vs `desktop-ctl` | `80-openwrt-desktop.rules` (`KERNEL=="card*"`) → `desktop-drm-udev-notify` (`/run/openwrt-desktop-drm/pending`) → `openwrt-desktop-drm.path`/`.service` → `/etc/init.d/desktop autostart`; `desktop-ctl` shares `/var/lock/procd_desktop.lock` via fd 1000 handoff | All start/stop/restart/autostart/switch operations serialized under `/var/lock/procd_desktop.lock`; `autostart` checks `manual-stop` inside lock and never clears it; `95-desktop` is a thin compat adapter skipping `OPENWRT_UDEV_HANDLED_DESKTOP=1` |
| ALSA `/dev/snd/*` user ACLs | `sound/95-desktop-audio`, `desktop-audio-permissions.init`, `desktop-audio-setup` (unlocked, non-atomic state file) | `80-openwrt-desktop-audio.rules` → `desktop-audio-udev-notify` (`/run/openwrt-desktop-audio/pending`) → `openwrt-desktop-audio-acl.path`/`.service` → locked `/usr/libexec/desktop-audio-permissions` | Single `flock` (`/run/openwrt-desktop-audio/lock`), reads latest UCI user inside lock, clears previous UID, tolerates vanished nodes mid-enumeration, atomic `acl-uid` update; `95-desktop-audio` waits on in-flight unit when `OPENWRT_UDEV_HANDLED_AUDIO=1` |
| Sunshine `/dev/uinput` ACL vs binary/KMS cap | `misc/95-sunshine`, `sunshine-permissions.init`, `sunshine-setup`, `postinst`, `desktop-ctl sync-sunshine` all ran full `sunshine-permissions` | Device events (`80-openwrt-sunshine.rules` → `openwrt-sunshine-uinput.path`/`.service`) invoke `sunshine-permissions --uinput-only` (touches `/dev/uinput` ACL only); install/setup/init/`sync-sunshine` invoke full `sunshine-permissions` | Single `flock` (`/run/openwrt-sunshine/lock`); `--uinput-only` never touches `/usr/bin/sunshine` or `setcap`; user switch/revocation cleans old ACLs and strips KMS cap |
| OpenWrt compat hotplug bridge | `openwrt-udev-forward` direct ubus `procd.udev event` (drops events if `procd`/`ubusd` down; no inflight crash isolation) | Single production path `/run/openwrt-hotplug/` (mode `0700`) with bounded queue (2,048 items / 8 MiB), `(boot_id, SEQNUM)` dedup, `inotify`-before-scan consumer, atomic `pending` → `inflight` → retirement, crash quarantine with per-device deferral, stale `DISKSEQ`/firmware checks, and `receiver.cap` two-step protocol switch | Legacy `procd.udev event` retained for mixed-version upgrades; read-only `queue_status` and operator `queue_resolve` (`discard`/`retry`) added |

### Baseline Race Reproduction (Unmodified Image, Isolated KVM VM)

Evidence: `build_dir/udev-migration-validation-20261125/baseline/baseline-results.json` (boot ID `627a405d-fa9a-455b-96ba-f15a8a7ecf3a`).

| Baseline failure | Observed reproduction |
| --- | --- |
| KVM double write / reversion | `/dev/kvm` started at `0660`, reverted to `0666` immediately after `udevadm trigger --action=add --settle /sys/class/misc/kvm`, and returned to `0660` only after rerunning `/usr/libexec/libvirt-openwrt-prepare` |
| DRM `renderD128` double write | After `udevadm trigger --action=add --settle /sys/class/drm/renderD128` (`mono=36.43`), node was `0666`; hotplug probe (`seq=1965`, `mono=36.44`) observed `0:43:666`; `zz-libvirt-render` changed it to `0660` asynchronously (`mono=37.43`) |
| `virtio-ports` duplicate symlink | udev created `/dev/virtio-ports/org.qemu.guest_agent.0 -> ../vport1p1`; `00-virtio-ports` failed with `rc=1` (`ln: failed to create symbolic link '/dev/virtio-ports/org.qemu.guest_agent.0': File exists`) |
| Desktop `manual-stop` vs DRM `change` TOCTOU | Confirmed in unmodified `95-desktop` (unlocked `[ ! -e /run/openwrt-desktop/manual-stop ]` check before `/etc/init.d/desktop start`) and `desktop.init` (`start_service` unconditionally runs `rm -f /run/openwrt-desktop/manual-stop` with no lock-protected guard); DRM `change` produced `seq=1967`/`1968` (`mono=40.16`/`40.17`) |

## 2. Candidate Artifacts & Source/Host Checks

### Signed Candidate APKs Built

| Package | File | SHA256 |
| --- | --- | --- |
| `procd` | `bin/systemd/packages/x86_64/base/procd-2026.11.03~fb611687-r11.apk` | `3c48cab246907b5c70ad85647fd165844e4b8cbee0bba840522652f060112a23` |
| `procd-ujail` | `bin/systemd/targets/x86/64-glibc/packages/procd-ujail-2026.11.03~fb611687-r11.apk` | `1356eb612a201d9e75954c6998171fc0158e95426902f27f27e0ac9115bdfa23` |
| `procd-seccomp` | `bin/systemd/packages/x86_64/base/procd-seccomp-2026.11.03~fb611687-r11.apk` | `dbf3f2980ae007e3272a3c8200a00df7baaf4a2fe42d17f6c275b4b5d6c94f83` |
| `libvirt-daemon` | `bin/systemd/packages/x86_64/base/libvirt-daemon-12.9.0-r5.apk` | `542144dbd262e73cf81c1c54ef3776dad904a5408dcef3c89a7b6c87297e7263` |
| `openwrt-desktop-base` | `bin/systemd/packages/x86_64/base/openwrt-desktop-base-46.apk` | `a3fbb2934d5abadfc2959962bb9e1f97166e1bf2ba5558ed7ad39e9a919a01f4` |
| `openwrt-desktop-audio` | `bin/systemd/packages/x86_64/base/openwrt-desktop-audio-1-r9.apk` | `689c63cf1e872e4b063a7d786f9bbc5a260b46f0aa3bcda14a58d247b9aef9be` |
| `sunshine` | `bin/systemd/packages/x86_64/base/sunshine-2026.914.233613-r17.apk` | `3de18802bca36a2135d12595ad4377cf32bff2755e12ce0bdbb87217bb315f66` |
| `virtio-console-helper` | `bin/systemd/packages/x86_64/packages/virtio-console-helper-11.1.3-r6.apk` | `31a16efd40e0aa9b7199d5505537c6265a7fda6897ac7647fe8f23026d47ed20` |

### Host & Package Validation

| Check | Result |
| --- | --- |
| `scripts/tests/test-procd-units.py` | 11/11 passed (including `libvirt-daemon` udev rules, non-daemon default preservation, `virtio-console-helper` native/non-systemd split, `udevadm verify`) |
| `scripts/tests/test-systemd-udev-boundary.py` | 3/3 passed |
| `scripts/tests/test-udev-hotplug-migration.py` | 10/10 passed (desktop fd-1000 `procd_lock` handoff, DRM notify/reconcile/backoff, `.path` cycle guard, audio user switch + vanished node tolerance, Sunshine `--uinput-only` KMS isolation + revocation, compiled C queue 4-process concurrency / dedup / 2048-item overflow / pruning / `receiver.cap`, merge audit tool strict + tamper + `e06e3a621b` checks) |
| `scripts/tests/test-desktop-sessions.py` | 7/7 passed |
| `scripts/tests/test-desktop-audio.py` | 3/3 passed |
| `scripts/tests/test-sunshine-gnome.py` | 2/2 passed |
| `scripts/tests/test-desktop-gpu-coldplug.py` | 4/4 passed |
| `scripts/tests/test-luci-desktop.py` | 4/4 passed |
| `scripts/tests/test-systemd-service-bridge.py` | 29/29 passed |
| `scripts/tests/test-custom-package-updates.py` | 58/58 passed |
| `scripts/tests/test-systemd-router-decoupling.py` | 12/12 passed |
| `scripts/audit-hotplug-merge.py` | Passed; 14/14 hotplug JSON files content-hash classified |
| `udevadm verify --no-style` (all 4 new `.rules`) | Passed (4/4 success, 0 fail) |
| `sh -n` on all 13 modified/new shell scripts | Passed |
| `git diff --check` (main tree and `feeds/packages`) | Passed |

## 3. Isolated Candidate VM Validation

### 3.1 Core 7-Stage Candidate Suite (Batches 2–4)

Evidence: `build_dir/udev-migration-validation-20261125/candidate/candidate-results.json`.
All 15 candidate signed APKs were installed offline onto a fresh copy-on-write clone of the baseline disk using `apk --no-network --repositories-file /dev/null --cache-dir /tmp/apk-cache`.

| Check | Result |
| --- | --- |
| Mixed-version online upgrade (`procd` upgraded before restart) | Passed: `receiver.cap` absent while old `procd` ran; new `openwrt-udev-forward` automatically fell back to legacy `procd.udev event` and delivered `change null mem`; after `systemctl restart openwrt-procd.service`, `procd.udev queue_status` reported `mode=queued`, `protocol_version=1` |
| Admin-modified hook retention & unmodified hook removal | Passed: locally modified `/etc/hotplug.d/drm/zz-libvirt-render` retained with notice; unmodified `/etc/hotplug.d/virtio-ports/00-virtio-ports` removed cleanly |
| 3 consecutive cold boots | Passed (boot IDs `7988716d...`, `65fc464a...`, `5cbb695d...`): `/dev/kvm` (`root:kvm 0660`) and `/dev/dri/renderD128` (`root:render 0660`) converged directly in udev, `/dev/virtio-ports/org.qemu.guest_agent.0 -> ../vport1p1` owned by udev, `queue_mode=queued`, `/run/procd-udev-coldplug` present |
| Real `open()` access matrix | Passed: `libvirt-qemu` opened `/dev/kvm` and `/dev/dri/renderD128`; `render`-group user opened `/dev/dri/renderD128` and was denied `/dev/kvm`; unprivileged user was denied both |
| 20 rounds KVM + `renderD128` trigger churn | Passed: 20/20 rounds kept `0660` immediately after `udevadm settle` (zero reversion to `0666`) |
| 20 rounds QMP `virtserialport` hot-unplug & re-plug | Passed: 20/20 rounds removed `/dev/virtio-ports/org.qemu.guest_agent.0` on unplug and recreated valid char-device symlink on re-plug |
| Desktop `manual-stop` vs DRM `change` burst + direct entries | Passed: 5x udev DRM `change`, `hotplug-call drm`, and `ubus call hotplug.drm call` preserved `manual-stop` and did not resurrect `openwrt-desktop.service` |
| Audio ACL live user switch (`alice` → `bob`) | Passed: udev `sound` event converged `/dev/snd/controlC0` ACL to `user:bob:rw-` and removed `user:alice` |
| Sunshine portal/KMS isolation & revocation | Passed: udev `uinput` event in portal mode granted `user:bob:rw-` on `/dev/uinput` with zero `cap_sys_admin` on `/usr/bin/sunshine`; KMS toggle granted `cap_sys_admin=p`; empty enrollment revoked `/dev/uinput` ACL and stripped `cap_sys_admin` |
| Third-party ordered scripts (`80-order-a`, `90-order-b`) via all 3 entry points | Passed: udev trigger, direct `/sbin/hotplug-call mem`, and `ubus call hotplug.mem call` each delivered in order with expected environment |
| Disconnect buffering (`openwrt-procd.service` stopped) | Passed: 2 real udev events (`null`, `zero`) buffered in `/run/openwrt-hotplug/pending/` without udev hang and drained in exact admission order after `procd` started |
| In-flight crash quarantine & per-device deferral (`SIGKILL` mid-handler) | Passed: killed `procd` after side-effect counter reached 1 while record `0000000000000205` was in `inflight/`; on restart moved to `quarantine/` (`reason=procd_crash_inflight`), side-effect count stayed 1 (zero auto-replay), subsequent `/dev/null` event deferred (`deferred >= 1`), different device `/dev/zero` dispatched immediately; `queue_resolve` (`action=discard`) unblocked deferred `/dev/null` cleanly |
| Corrupt record, stale `diskseq`, expired firmware | Passed: malformed JSON moved to `corrupt/` (`corrupt_total=1`), mismatched block `diskseq` and expired firmware skipped (`expired` incremented) without blocking healthy events |
| `libvirt-daemon` live uninstall & reinstall (`0666` ↔ `0660`) | Passed: `apk del --rdepends libvirt-daemon` removed `65-libvirt-devices.rules` and restored `0666` on `/dev/kvm` and `/dev/dri/renderD128` via `postrm`; `apk add` restored `0660` via `postinst` |
| `scripts/tests/procd-units-guest.sh` | Passed end-to-end inside candidate VM (including `openwrt-procd.service` restart without repeating coldplug) |

### 3.2 Suite A — Extended Device, `qemu-ga`, `ubusd`, `fstools`, Overflow & TPM2 VM Checks

Evidence: `build_dir/udev-migration-validation-20261125/extra-checks/extra-results.json` (candidate APKs + `qemu-ga` `11.1.3` + `swtpm` TPM2 + unix-socket `virtserialport` + `virtio-scsi` hot-pluggable ext4 spare disk).

| Check | Result |
| --- | --- |
| A1: TPM2 (`swtpm`) device boundary & `systemd-creds` | Passed: `dev-tpmrm0.device`, `dev-tpm0.device`, `tpm2.target` all `active`; `/dev/tpmrm0` present; `systemd-creds encrypt --with-key=tpm2` / `decrypt` round-tripped cleanly across cold boot |
| A2: `qemu-ga` live RPC + QMP `virtserialport` hot-unplug & re-plug | Passed: `00-virtio-ports` absent, `10-qemu-ga` active, `/dev/virtio-ports/org.qemu.guest_agent.0 -> ../vport2p1` owned by udev; `guest-ping` & `guest-info` (`11.1.3`) succeeded over host Unix socket; after `device_del`, symlink vanished; after stopping `qemu-ga` and `device_add`, udev recreated symlink, `10-qemu-ga` restarted `qemu-ga` (`PID 7286`), and `guest-ping` succeeded again |
| A3: `ubus subscribe hotplug.mem` + `ubusd` pause (`SIGSTOP`/`SIGCONT`) & stop/start | Passed: `ubus subscribe hotplug.mem` received JSON `"event"` notification (`"SUBSYSTEM":"mem"`); during `ubusd` `SIGSTOP`/`SIGCONT`, udev did not hang, `procd` kept the same PID and delivered once; during `openwrt-ubusd.service` stop, 2 real events queued (`pending_down=2`, `count_down=0`) and drained once each (`count_after=2`) after start |
| A4: `queue_resolve` with `action="retry"` after inflight `SIGKILL` | Passed: record `0000000000000087` quarantined on mid-handler `SIGKILL` (`before=1`); explicit `ubus call procd.udev queue_resolve '{"id":"0000000000000087","action":"retry"}'` re-executed handler (`after=2`) and cleared quarantine |
| A5: Vanished block device `remove` semantics | Passed: `SUBSYSTEM=block ACTION=remove DEVPATH=/devices/virtual/block/nonexistent_vdz DISKSEQ=999999` was delivered to `/etc/hotplug.d/block/99-remove-probe` (not dropped by `diskseq` staleness check) |
| A6: Live VM 2,048-item queue overflow cap | Passed: with `procd` stopped and 2,048 pending records populated, 2,049th `openwrt-udev-forward` call preserved all 2,048 accepted items and incremented `queue_status.overflow=1` |
| A7: Spare ext4 data disk `fstools` mount & hot-remove | Passed: hot-attaching 32 MiB ext4 disk (`LABEL=UDEVDATA`) via `virtio-scsi` triggered `fstools`/`block` mount at `/mnt/sda` (`fstools-mount-ok` read back, no conflicting systemd `.mount` unit); QMP `device_del` unmounted and cleaned node (`UNMOUNTED`) |

### 3.3 Suite B — Pure-Router + LAN Client + PPPoE AC + Failsafe VM Regression

Evidence: `build_dir/udev-migration-validation-20261125/pure-router/pure-router-results.json`.
Installed clean pure-router base (`components: []`, 1,047 packages, zero desktop/libvirt packages) from `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-installer.iso` (SHA256 `53566d432e8b1a743a7521e0dcbc7c8896ac76300262d7ca6f01e25187d697f5`) and upgraded candidate `procd-2026.11.03~fb611687-r11.apk` (+ `procd-ujail`, `procd-seccomp`).

| Check | Result |
| --- | --- |
| B1: Pure-router cold boot, zero desktop units & single coldplug replay | Passed: PID 1 `systemd`, `procd` `2026.11.03~fb611687-r11`, `queue_status.mode=queued`, zero `openwrt-desktop*` packages/units; `/run/procd-udev-coldplug` inode/mtime unchanged across `systemctl restart openwrt-procd.service` (probe confirmed zero re-coldplug replay while subsequent live trigger delivered once) |
| B1: `preinit` / `failsafe` recovery | Passed: `kernelctl check` & `migrate`, booted `owrt-rescue-failsafe` (`failsafe=true`, PID 1 `init`), ran `mount_root`, persisted `/etc/failsafe-check`, rebooted cleanly (`plain_reboot`) back to `systemd` PID 1 with `queue_mode=queued` |
| B2: 3-VM PPPoE AC + Pure Router + LAN Client | Passed: `pppoe-ac` (`rp-pppoe-server-4.0-r3`) + `pppoe-router` + `pppoe-client` verified PPPoE dial (`pppoe-wan`), LAN DHCP lease, DNS (`pppoe.test`), NAT HTTP fetch, **LuCI HTTPS login** (`ubus session.login`), **SSH ed25519 key login**, UCI firewall rule add + `/etc/init.d/firewall reload` (`masquerade` intact), and **PPPoE AC disconnect + router redial** (`pppd` PID `7218` → `9473`) with LAN NAT restored (`quarantined=0`) |

### 3.4 Suite C — Graphical GNOME 51 & KDE Plasma 6.8.3 + Audio + `xfreerdp3` + Sunshine VM Checks

Evidence: `build_dir/udev-migration-validation-20261125/desktop-sessions/desktop-sessions-results.json`, `xfreerdp3-gnome.log`, `xfreerdp3-plasma.log`.
Booted 4 GiB / 4 vCPU KVM guest with `virtio-vga-gl` (`egl-headless,rendernode=/dev/dri/renderD128`), `intel-hda` + `hda-duplex`, `usb-kbd` + `usb-tablet`, `swtpm` TPM2, all 15 candidate APKs (`procd-r11`, `desktop-46`, `audio-r9`, `sunshine-r17`, `libvirt-r5`, `virtio-console-helper-r6`), plus KDE Plasma 6.8.3 from the same-build ISO offline repo.

| Check | Result |
| --- | --- |
| C1: GNOME 51 cold-boot Wayland session & TPM2 keyring | Passed: `desktop-ctl --json status` reported `session=gnome`, `session_ready=true`, `keyring_credential=tpm2`, `keyring_unlocked=true`, `outputs=["Virtual-1"]`; `/etc/desktop/gnome/32771.keyring-passphrase.cred` present; all 3 `.path` units (`drm`, `audio-acl`, `sunshine-uinput`) `active` |
| C1: PipeWire & ALSA signal check (GNOME) | Passed: `pw-play` (`peak=12000, rms=6625.5`), `aplay` (`peak=12000, rms=6585.5`) captured via `parec`, `arecord` captured `48000` frames |
| C1: Sunshine portal ↔ KMS ↔ portal & live HTTPS 47990 | Passed: portal mode had `cap_portal=[]`, `/dev/uinput` ACL `user:alice:rw-`, service `active`; `--enable-kms` granted `cap_sys_admin=p` and live HTTPS `https://192.0.2.1:47990/` returned `HTTP 307`; switching back to `--capture=portal` stripped `cap_sys_admin` (`cap_back=[]`) |
| C1: Real host `xfreerdp3` (`3.33.1`) under `Xvfb` to GNOME RDP | Passed: `connected=true`, `rdpsnd_activity=true`, keystroke sent cleanly |
| C1: Live `desktop-ctl action stop` vs DRM `change` burst + restart | Passed: 5x `udevadm trigger --action=change /sys/class/drm/card0` did not resurrect stopped GNOME session; `desktop-ctl action start` restored `session_ready=true` |
| C2: LuCI HTTPS RPC switch GNOME → KDE Plasma 6.8.3 | Passed: `luci.desktop switch {"session":"plasma"}` returned `switched=true`; Plasma reached `session_ready=true`, `keyring_credential=tpm2`, `keyring_unlocked=true`; Konsole Wayland ran (`KONSOLE_WAYLAND_OK`); PipeWire/ALSA signal passed (`pw-play rms=6546.2`, `aplay rms=6585.5`, `arecord 48000` frames); Sunshine `active` (`HTTP 307`) |
| C2: Real host `xfreerdp3` (`3.33.1`) under `Xvfb` to KRdp | Passed: `connected=true`, `rdpsnd_activity=true`, Chinese clipboard synced verbatim (`你好OpenWrt Plasma剪贴板测试`, `clipboard_match=true`) |
| C3: LuCI HTTPS RPC switch Plasma → GNOME | Passed: `luci.desktop switch {"session":"gnome"}` restored GNOME `session_ready=true`, `rdp_active=true`, `sunshine_active=true`, `audio_active=true`; `queue_status` reported `mode=queued`, `dispatched=239`, `pending=0`, `quarantined=0`, `overflow=0`, `corrupt=0` |

### 3.5 Physical Router Verification (`192.0.2.1`, Post-Publication & User Reboot)

Published snapshot: `/srv/openwrt-feeds/public/snapshots/20261125T083350.498186Z` (23 changed userspace APKs; kernel unchanged at `7.3.6-87-openwrt`), upgraded via `apk update && apk upgrade` (`uci-history` revision `109`), followed by user-initiated cold reboot (boot ID `<redacted>`).

| Check | Result |
| --- | --- |
| Systemd & service health | `systemctl is-system-running` = `running`, `0` failed units; `openwrt-ubusd`, `openwrt-procd`, `openwrt-services`, `openwrt-network@instance1`, `openwrt-dnsmasq@cfg01411c`, `openwrt-daed@daed`, `dev-tpmrm0.device`, `tpm2.target`, and all 3 new `.path` units (`openwrt-desktop-drm.path`, `openwrt-desktop-audio-acl.path`, `openwrt-sunshine-uinput.path`) all `active` |
| `procd` queued compatibility bridge | `ubus call procd.udev queue_status`: `mode="queued"`, `protocol_version=1`, `dispatched=192`, `pending=0`, `inflight=0`, `deferred=0`, `quarantined=0`, `overflow=0`, `corrupt=0`; `/run/openwrt-hotplug` mode `0700`, `receiver.cap` bound to current boot ID and PID `1522`; `/run/procd-udev-coldplug` present |
| Device permissions & ACLs | `/dev/kvm` (`root:kvm 0660`), `/dev/dri/renderD128` (`root:render 0660`), `/dev/uinput` (`root:video 0660`, ACL `user:desktop-user:rw-`), `/dev/snd/controlC0` (`root:audio 0660`, ACL `user:desktop-user:rw-`), `/dev/tpmrm0` (`root:root 0600`), `/usr/bin/sunshine` caps empty (`portal` mode); old `zz-libvirt-render` and `00-virtio-ports` hooks removed |
| Physical desktop & libvirt VM | `desktop-ctl --json status`: KDE Plasma 6.8.3 (`desktop-user`, physical `HDMI-A-2`), `keyring_credential=tpm2`, `keyring_unlocked=true`, `session_ready=true`, `rdp_active=true`, `sunshine_active=true`, `audio_active=true`, `n_restarts=0`; `virsh list --all`: `guest-vm` `running` |
| Restart hygiene & boot journal | `needrestart --json`: `0` services, `0` applications, `0` warnings pending; `journalctl -b -p warning..err` matched zero `procd`/`udev`/`hotplug`/`desktop`/`sunshine`/`libvirt`/`tpm` warnings or errors |

### Defects Caught & Fixed During Candidate VM Testing

1. **Cold-boot `.path` ordering cycle**: `openwrt-desktop-drm.path` originally had `After=openwrt-services.service`, which conflicted with `DefaultDependencies=yes` (`Before=paths.target` → `Before=basic.target` → `Before=openwrt-procd.service` → `Before=openwrt-services.service`), causing systemd to drop `openwrt-procd.service` on cold boot. Fixed by removing `After=openwrt-services.service` from `openwrt-desktop-drm.path` (retaining ordering on `openwrt-desktop-drm.service`) and adding a host unit test guard.
2. **`.path` burst limit under 20-round churn**: `TriggerLimitBurst=20` in `TriggerLimitIntervalSec=10s` tripped `trigger-limit-hit` during rapid 20-round `renderD128` churn. Fixed by narrowing `80-openwrt-desktop.rules` to `KERNEL=="card*"` and raising `TriggerLimitBurst=200` on all three `.path` units.
3. **`50-udev-default.rules` `ACTION=="add"` guard on `postrm`**: `50-udev-default.rules` jumps past its `MODE="0666"` lines when `ACTION!="add"`, so `postrm`'s `--action=change` did not restore `0666` on uninstall. Fixed by issuing targeted `--action=add` triggers on `misc/kvm` and `drm/renderD*` only in `libvirt-daemon`'s `postinst` and `postrm`.

## 4. Validation Scope & Remaining Gaps

- **Completed in this pass**:
  - All host/source/package checks (142/142 unit tests, `audit-hotplug-merge.py`, `udevadm verify`, `sh -n`, `git diff --check`) and all 6 modified package families built & signed cleanly.
  - All isolated KVM VM acceptance suites from Section 5 of `docs/systemd-udev-hotplug-migration-plan.md`: Baseline race reproduction, 7-stage Core Candidate Suite, Suite A (`qemu-ga`, `ubusd`, `queue_resolve retry`, vanished block `remove`, 2,048 overflow, `fstools` spare disk, TPM2), Suite B (pure-router + 3-VM PPPoE AC/LAN client/LuCI/SSH/firewall/failsafe), and Suite C (graphical GNOME 51 + KDE Plasma 6.8.3 + PipeWire/ALSA signal + real `xfreerdp3` client + Sunshine portal/KMS).
  - Authorized LAN APK feed publication (`/srv/openwrt-feeds/public/snapshots/20261125T083350.498186Z`), physical router (`192.0.2.1`) package upgrade, and read-only post-reboot verification (boot ID `<redacted>`).
- **Not executed in this pass**:
  - Full combined firmware image / ISO rebuild from scratch.
  - Interactive physical-client stress tests on physical USB audio hotplug or physical Moonlight streaming client (VM audio signal, `xfreerdp3`, and Sunshine portal/KMS checks passed in Suite C).
