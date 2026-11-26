# `scripts/tests/` Test Index

This directory holds host unit tests, LuCI frontend assertions, KVM/VM drivers, disposable guest smoke scripts, and C probes/fixtures. All scripts keep flat top-level paths (except `kernel-upgrade/vm-console.py`) so documentation and validation commands remain stable.

## Running Host Tests

Use `run-host-tests.py` from the repository root to list or run host-safe tests without invoking KVM/VM drivers or target-only router checks:

```sh
python3 -B scripts/tests/run-host-tests.py --list --verify-inventory
python3 -B scripts/tests/run-host-tests.py --suite publish
python3 -B scripts/tests/run-host-tests.py --suite systemd --suite luci -j4
python3 -B scripts/tests/run-host-tests.py --suite all -j4
python3 -B scripts/tests/run-host-tests.py --suite staged
```

Suites:

- `publish`: APK, ELF/ucode ABI, rebuild diagnosis/allocation, LAN feed publication, upgrade preflight, kernel generation/packaging/updates, custom package updaters, parallel build staging, scheduled maintenance.
- `systemd`: native systemd/procd/udev boundaries, hotplug migration, service bridge, SSH/Samba/NAS/auxiliary units, journald/logd, needrestart, irqbalance, merged `/usr`, backup CLI.
- `desktop`: GNOME/Plasma session switcher, RDP config/listener/audio latency, keyring bootstrap, PipeWire audio, Fcitx5 IME, Sunshine, GPU coldplug, icon theme hook, rtkit, Flatpak/Podman/libvirt host checks.
- `luci`: ucode RPC backend tests (`test-luci-*.py`), C runtime guard (`test-luci-podman-runtime.py`), and Node.js view tests (`test-luci-*.js`, `test-sshd-startup-view.js`).
- `installer`: whole-disk installer core, optical bootstrap, and 10-component offline catalog.
- `audit`: `router-audit` and `uci-history` host unit tests.
- `staged` (opt-in): `test-custom-branch-upgrade.py` runs Node/npm and GJS with the staged x86_64 desktop libraries and verifies the weather database and calendar server linkage. Build the desktop packages before running this suite.
- `legacy` (opt-in via `--suite legacy` or `--include-legacy`): tests for disabled optional/legacy recipes kept in tree (`test-desktop-launcher.py`).

The summary counts scripts. `PARTIAL` means the script succeeded with a mix of completed and skipped tests. Use `-v` to see the underlying unittest report.

The D-Bus boot-readiness test follows the adapter selected by the package recipe. On systemd, `start`, `restart` and `reload` request a start of `dbus.service`. The `boot` action returns immediately. During offline installation, enablement queries and changes use the installation root.

### Legacy Weston IME acceptance

With a staged Weston RDP backend and desktop IME packages, run `python3 scripts/tests/desktop-ime-smoke.py` explicitly. It builds `desktop-ime-entry.c` and `desktop-ime-rdp.c`, drives the Pinyin and English toggles over RDP, checks the committed text `你好abc` and saves a candidate screenshot. The default desktop profile uses GNOME or Plasma. See the [GNOME desktop validation](../../docs/gnome-desktop-validation.md) for the current GNOME input checks.

## Non-Host Test Categories

### KVM / VM Drivers (Host-driven QEMU, disposable disks only)

- `kernel-upgrade/vm-console.py`: JSON-line serial controller for disposable EFI/BIOS OpenWrt VMs (also used by `test-apk-transaction-vm.py`).
- `gnome-desktop-vm.py`: JSON-line serial controller for disposable Q35 GNOME desktop VMs.
- `test-apk-transaction-vm.py`: interrupted APK transaction recovery in a disposable VM.
- `test-daed-vm.py`: core 28-check router + LAN client KVM validation for `daed`.
- `test-daed-client-features-vm.py`: extended KVM validation (V01–V11) for `daed` client policy center, subscriptions, and real VLESS acceptance.
- `test-installer-iso-vm.py`: hybrid USB/CD-ROM installer ISO KVM harness (imported by `test-installer-components-vm.py` and `test-kde-plasma-vm.py`).
- `test-installer-components-vm.py`: disposable KVM acceptance for selectable installer components.
- `test-kde-plasma-vm.py`: disposable KVM validation for KDE Plasma 6.8.3.
- `test-systemd-router-pppoe-vm.py`: pure-router UEFI KVM validation (systemd PID 1, failsafe, PPPoE AC, LAN NAT).
- `test-uci-history-vm.py`: exact-image KVM gate for `uci-history` rollback and reboot recovery.
- `test-input-hotplug.py`: procd/libudev input hotplug probe against a running disposable QEMU VM (`--no-desktop` for non-desktop images; pairs with `input-hotplug-monitor.py`).
- `spice-gl-reset.py`: SPICE pending-draw reset and input teardown check in a disposable VM.

### Disposable Guest & Target Smoke Scripts

> **Self-contained rule**: Guest scripts are uploaded individually into disposable VMs or targets. Do not add relative imports to host modules under `scripts/tests/`.

- **Systemd / Supervision / Logging / Services**: `systemd-guest-smoke.sh`, `systemd-permissions-smoke.sh`, `boot-readiness-guest.py`, `procd-units-guest.sh`, `systemd-service-bridge-guest.py`, `systemd-cgroup-guest.py`, `systemd-cgroup-services-guest.py`, `journald-guest-smoke.sh`, `logd-journal-guest.py`, `sshd-systemd-guest.py`, `samba4-systemd-guest.py`, `nas-systemd-guest.py`, `auxiliary-systemd-guest.py`, `needrestart-guest.py`, `podman-systemd-guest-smoke.sh`.
- **Desktop / Browser / Audio / Streaming**: `desktop-kernel-smoke.py`, `gnome-desktop-guest.py`, `gnome-desktop-router-guest.py`, `gnome-desktop-input.py`, `gnome-desktop-renderer.py`, `gnome-desktop-stream-surface.py`, `gnome-desktop-https.js`, `gnome-desktop-runtime.js`, `desktop-audio-guest.py`, `desktop-client-audio.py`, `firefox-smoke.sh`, `firefox-vaapi-guest.py`, `sunshine-stream-probe.py`, `sunshine-stream-metrics.py`, `input-hotplug-monitor.py`.
- **Virtualization / SPICE**: `libvirt-guest-smoke.sh`, `virt-manager-smoke.sh`, `spice-gl-console.py`, `virtio-spice-smoke.py`, `test-libvirt-secondary-drivers.py` (target-only with `sudo`).

### C Probes & Fixtures

- Host/unit-test C fixtures: `irqbalance-affinity-capture.c` (used by `test-irqbalance-netdev-cpus.py`), `logd-journal-record.c` and `logread-reconnect.c` (used by `test-logd-journal.py`).
- Target/guest C probes: `appimage-probe.c`, `appimage-glx-probe.c`, `desktop-seat-retirement.c`, `distrobox-gtk-probe.c`, `flatpak-portal-probe.c`, `sunshine-stream-client.c`, `virtio-egl-probe.c`.

For Sunshine CPU metrics, run `desktop-capture-snapshot.py` as the desktop user before and after the stream. Save its output as `<prefix>-before.json` and `<prefix>-after.json` alongside the capture consumed by `sunshine-stream-metrics.py`.

### Offline Helpers & Audit Tools

- `audit-firefox.py`: audits ELF dependencies and private library isolation in an extracted target rootfs.
- `build-needrestart-fixtures.py`: builds target ELF fixtures for `needrestart-guest.py`.
- `router-audit-fixtures.py`: builds synthetic `router-audit` puller databases (imported by `test-router-audit.py` and `router-audit-llm-eval.py`).
- `router-audit-llm-eval.py`: scores a local OpenAI-compatible model against `router-audit` fixtures.

## Related Scripts in `scripts/`

- `scripts/test-image-network.py`: shared KVM boot/network harness used by `scripts/scheduled-maintenance.py` and multiple `test-*-vm.py` suites.
- Target smoke scripts documented directly in feature guides: `scripts/test-appimage.sh`, `scripts/test-distrobox.sh`, `scripts/test-full-utils.sh`, `scripts/test-native-app-deps.sh`, `scripts/test-native-build-tools.sh`, `scripts/test-native-libs.sh`, `scripts/test-podman-rootless.sh`.
