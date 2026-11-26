# GEMINI.md

This file provides project memory, architectural context, and operational rules for Gemini / Antigravity when working in this repository.

---

## 1. Project Overview & Core Divergences

This repository is a heavily customized OpenWrt fork tracking `openwrt/openwrt` `main` (450+ commits ahead; check live Git refs). It targets `x86/64` as a combined **router plus general-purpose Linux desktop/virtualization/container host** built on foundations that differ from stock OpenWrt:

- **C Library (`glibc`)**: Uses `glibc` instead of `musl` (`CONFIG_LIBC_USE_GLIBC=y`, `CONFIG_USE_GLIBC=y`), with Debian multiarch compatibility (`/lib/x86_64-linux-gnu`, `/usr/lib/x86_64-linux-gnu`) via `glibc-distro-compat`.
- **Package Manager (`APK`)**: Uses signed APK packages (`CONFIG_USE_APK=y`, `CONFIG_SIGNED_PACKAGES=y`) with explicit ELF SONAME (`so:<SONAME>=0`) and ucode ABI contracts instead of `opkg`.
- **Init & Supervision (`native systemd` + `procd`)**: Runs native `systemd` (`262-r15`) as the sole x86/64 PID 1 (`CONFIG_OPENWRT_SYSTEMD=y`) with a merged `/usr` filesystem (`scripts/merge-usr.py`) and reviewed `99-systemd.rules` device boundaries (`docs/systemd-udev-boundary.md`), while retaining `procd` as the OpenWrt ubus/hotplug/rc service API. `samba4`, `wsdd2`, and `avahi-daemon` run natively in `nas.slice`; `cron`, `nlbwmon`, and `ddns-go` run natively in `auxiliary.slice`.
- **Kernel (`Mainline Linux 7.3`)**: Target `x86/64` runs mainline Linux 7.3 (`CONFIG_LINUX_7_3=y`, currently 7.3.5, toolchain `GCC 15.3.0`, with `CONFIG_GRUB_BOOTOPTS="split_lock_detect=off"`); `6.18` kernel configs/patches are retained alongside it. Kernels ship as parallel, ABI-pinned distribution packages (`linux-image-<kver>-<gen>-openwrt`) managed on-device by `kernelctl`, with automatic reuse of verified published generations when kernel inputs are unchanged (`docs/kernel-generation-reuse-plan.md`).
- **Desktop Stack (`GNOME 51` & `KDE Plasma 6.8.3`)**: Decoupled shared-user Wayland desktop on VT7 (`openwrt-desktop-base`, `desktop-ctl`, `luci-app-desktop`, TPM2-sealed keyring credentials) supporting both GNOME 51 (`openwrt-desktop`) and KDE Plasma 6.8.3 (`openwrt-desktop-plasma`, Qt 6.11.3, KF6 6.32.0, Konsole), started via PAM/logind without a display manager, shared over LAN IPv4 RDP (`gnome-remote-desktop` / `krdp`) and Sunshine/Moonlight, with Fcitx5 (`openwrt-desktop-ime` / `-plasma`), PipeWire (`openwrt-desktop-audio`), `firefox-esr-bin`, and `google-chrome-bin`.
- **Core Build-System Surgery**: Directly modifies upstream build and core files (`include/kernel.mk`, `include/package-pack.mk`, `include/package.mk`, `include/rootfs.mk`, `package/base-files`, `package/system/{apk,procd,systemd}`, `package/network/{services/dnsmasq,utils/nftables,config/firewall4}`, `package/libs/libnftnl`, `target/linux/x86/image`).

Build outputs:
- **Native systemd firmware & APK feeds**: `bin/systemd/` (e.g., `bin/systemd/targets/x86/64-glibc/`).

---

## 2. Essential Commands

### Feeds & Custom Package Updates
```bash
./scripts/feeds update -a          # Fetch feeds, init luci-theme-argon submodule, AND run update-custom-packages.py --update
./scripts/feeds update -i -a       # Regenerate feed indexes ONLY without querying upstream versions
./scripts/feeds install -a         # Populate symlinks in package/feeds/
```
- `./scripts/feeds update -a` automatically queries upstream versions and updates recipes listed in `configs/custom-package-updates.json` (including `companion_assets` SHA-256 hashes). Inspect local work before running, and use `-i -a` when you only want index regeneration.
- Every recipe under `package/custom/` **must** be registered in `configs/custom-package-updates.json` (`series`, `major`, `stable`, `follow`, or `local`), or the updater fails.

### Configuration Management
```bash
make defconfig                     # Normalize existing .config
make prereq                        # Verify host prerequisites
make download                      # Prefetch source archives into dl/

# Merge a feature fragment into .config (never overwrite .config with the full snapshot unprompted):
./scripts/kconfig.pl + .config configs/<feature>.config > .config.new && mv .config.new .config && make defconfig
```
- **Full Snapshots**: `configs/x86-64-systemd-desktop.config` is the tracked full GNOME desktop configuration snapshot (`cp configs/x86-64-systemd-desktop.config .config && make defconfig`), and `configs/x86-64-systemd-router.config` is the standalone pure-router profile. Merge `configs/plasma-packages.config` or `configs/plasma.config` when building KDE Plasma packages or the 10-component installer ISO. Working `.config` may sit at a newer `CONFIG_OPENWRT_KERNEL_SEQUENCE` and carry local optional selections.
- Do **not** rely on `scripts/diffconfig.sh` to minimize `.config`; circular Kconfig dependencies (`video-support`, `openwrt-desktop`, `glib2-gir`, Mesa) break minimization.

### Building & Patch Refreshing
```bash
make -j3 V=s                                              # Build configured firmware (plain make does NOT reserve a kernel generation)
make package/custom/<name>/compile V=s                    # Build a single custom package
make target/linux/compile V=s                             # Build kernel only
make package/<name>/prepare V=s                           # Unpack and apply patches for a package
make package/<name>/refresh V=s                           # Regenerate quilt patches for a package
make target/linux/refresh V=s                             # Regenerate quilt patches for the kernel
python3 scripts/build-and-publish.py build-only -j12 V=s  # Full build without publishing, with kernel generation checks
```

### Publication & Kernel Maintenance
```bash
./scripts/build-and-publish.sh -j16                       # Build + preflight + publish userspace APKs and kernel generation
./scripts/publish-changed-feeds.sh [--dry-run]            # Run live-router preflight simulation, then publish changed APKs
python3 scripts/update-mainline-kernel.py --check|--update # Compare Linux 7.3 series against kernel.org / update point release
```

---

## 3. Architecture & Subsystems

### 3.1 Systemd-Only Init & Native Supervision
- **Boot path**: On x86/64, systemd is the sole normal init (`docs/systemd-only-plan.md`). OpenWrt preinit mounts the overlay and hands PID 1 to systemd. The native failsafe console uses `failsafe=true`.
- **Integration (`package/system/systemd-openwrt/`)**:
  - `openwrt-ubusd.service`: Runs `ubusd`.
  - `openwrt-procd.service`: Runs `procd --systemd=units`. `procd` (`r12`) remains the ubus service/system/hotplug API and consumes `/etc/hotplug.d` and `/etc/rc.button` handlers forwarded directly by `systemd-udevd` via `openwrt-udev-forward` (`procd.udev event`, without an intermediate filesystem queue; patch `150-systemd-udev-hotplug-queue.patch` removed), while each normal service instance registered via `procd.sh` becomes a transient `openwrt-SERVICE@INSTANCE.service` under `openwrt-SERVICE.slice` (procd patch `130-systemd-transient-units.patch`). Instances requiring `vrf`, `trace`, `bundle`, or descriptor passing fall back to procd children in `openwrt-*.scope`.
  - `openwrt-services.service`: Runs enabled `/etc/init.d/*` rc scripts in sequence.
  - `openwrt-network-wait-online.service`: Holds `network-online.target` until `netifd` brings up autostart static local interfaces (e.g., `lan`), up to 120s.
- **CLI Service Bridge (`package/system/systemd-openwrt-services/`)**:
  - Maps `systemctl start|stop|restart|reload|enable|status openwrt@NAME.service` onto `/etc/init.d/NAME`. Excludes `dbus`, `sshd`, `samba4`, `wsdd2`, `avahi-daemon`, `cron`, `nlbwmon`, `ddns-go`, `podman`, `apk-resume` (which use native units), and the old `umount` script, while classifying `wifi_schedule` and other one-shot setup scripts in `files/service-kinds`. PID 1 refuses direct start/stop/restart/reload jobs on transient `openwrt-SERVICE@INSTANCE.service` units from non-procd clients so init script hooks are not bypassed.
- **Device, NAS & Auxiliary Supervision Boundaries**:
  - `systemd-udev` (`262-r15`, rules added in r14) installs a reviewed subset (`package/system/systemd/files/99-systemd.rules`) restoring `.device` units (including `dev-tpmrm0.device`) without moving network, mount, or driver-loading policy from `netifd`/`fstools`/`blockd` (`docs/systemd-udev-boundary.md`). Single-writer device rules live in `libvirt-daemon` (`65-libvirt-devices.rules` for `0660` KVM/render), `virtio-console-helper` (omits `00-virtio-ports` on native systemd), and `openwrt-desktop-base`/`openwrt-desktop-audio`/`sunshine` (`80-openwrt-*.rules` + `.path`/oneshot reconcilers); `scripts/audit-hotplug-merge.py` guards upstream/feed hotplug merges (`docs/systemd-udev-hotplug-migration-validation.md`).
  - `samba4`, `wsdd2`, and `avahi-daemon` run as native static systemd units under `nas.slice` (`CPUWeight=100`, sibling of `openwrt.slice`), and `cron`, `nlbwmon`, and `ddns-go` run natively under `auxiliary.slice` (`docs/samba4.md`, `docs/nas-systemd.md`, `docs/auxiliary-systemd.md`).
- **Merged `/usr` (`scripts/merge-usr.py`)**:
  - Invoked from `include/package-pack.mk` and `include/rootfs.mk` to rewrite `/bin`, `/sbin`, `/lib` into `/usr/...`. `ALTERNATIVE_COMMANDS` handles BusyBox applet collisions (`dmesg`, `mount`, `passwd`, `ping`, `reboot`, etc.).

### 3.2 Whole-Disk USB & Optical Installer ISO
- Enabled via `configs/installer-iso.config` (`CONFIG_INSTALLER_ISO_IMAGES`), producing `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-installer.iso`.
- Built with a clean base router/ops squashfs (only git-tracked `files/` defaults; personal untracked overlays excluded) plus an embedded same-build signed offline APK repository for ten optional components (`configs/installer-components.json`: `gnome`, `plasma`, `audio`, `ime`, `rdp`, `sunshine`, `flatpak`, `appimage`, `virtualization`, `containers`). Requires `CONFIG_SIGNED_PACKAGES=y` and all ten component packages (`x86-64-systemd-desktop.config` + `plasma-packages.config` or `plasma.config`).
- Boots via hybrid BIOS/UEFI from raw USB (partition 3) or optical/virtual SATA CD-ROM (external initramfs loop-mounts the appended plain-LZ4 squashfs read-only) with `fstools_overlay=tmpfs` into an English whiptail TUI (`package/custom/openwrt-installer`, supports `openwrt-installer --answers FILE [--dry-run]`).
- Creates a fresh GPT (p128 BIOS gap, p1 FAT32 ESP `/boot`, p2 read-only `rootfs` squashfs, p3 `rootfs_data` overlay with `ext4`/`btrfs`/`xfs`, optional p4+ data partitions), installs selected components offline, configures LAN/WAN/firewall/accounts, and schedules a firstboot unit for optional regular user + `desktop-setup` (supporting `desktop_session` and `desktop_autostart`). See `docs/installer-iso.md`.

### 3.3 Shared Desktop Stack (GNOME 51 & KDE Plasma 6.8.3), Audio, IME & Remote Access
- **Decoupled packages**: `openwrt-desktop-base`, `openwrt-desktop-keyring`, `openwrt-desktop-rdp-base`, `openwrt-desktop-core` / `openwrt-desktop-rdp` / `openwrt-desktop` (`r46`, GNOME 51), `openwrt-desktop-plasma-core` / `openwrt-desktop-plasma-rdp` / `openwrt-desktop-plasma` (KDE Plasma 6.8.3, Qt 6.11.3, KF6 6.32.0, KRdp), `luci-app-desktop`, `openwrt-desktop-ime-base` / `-ime` / `-ime-plasma` (Fcitx5), `openwrt-desktop-audio` (`1-r9`, PipeWire + WirePlumber + PulseAudio compat), `openwrt-flatpak-base` / `openwrt-flatpak`, `openwrt-appimage`, `sunshine` (`r17`), `firefox-esr-bin`, and `google-chrome-bin`.
- **Session model**: Runs as an ordinary user on VT7 via PAM/logind (`openwrt-desktop.service`), with pluggable session plugins under `/usr/libexec/openwrt-desktop/sessions.d/` (`gnome`, `plasma`) managed via `desktop-ctl` and LuCI `Services -> Desktop`. Shares the local Wayland display over LAN IPv4 RDP (`gnome-remote-desktop` / `krdp`) and Sunshine/Moonlight. Keyring bootstrap secrets live under root-only `/etc/desktop/gnome/` (shared by GNOME and Plasma); when TPM2 is available, `desktop-setup` seals `UID.keyring-passphrase.cred` to the TPM2 SRK via `LoadCredentialEncrypted` (falling back to plaintext `LoadCredential` otherwise), and `desktop-gpu-coldplug` waits briefly for `/dev/tpmrm0`.
- **On-device provisioning commands (run as root)**:
  ```sh
  desktop-setup USER [--no-autostart]
  desktop-rdp-setup USER [--session gnome|plasma] [--password-stdin]
  sunshine-setup USER --capture=portal|--enable-kms
  desktop-audio-setup USER
  desktop-ctl status|switch|action ...
  ```
- See `docs/gnome-desktop.md`, `docs/kde-plasma.md`, `docs/desktop-session-switcher.md`, `docs/desktop-ime.md`, `docs/desktop-audio.md`, and `docs/google-chrome.md`.

### 3.4 Mainline Kernel & Parallel Generations
- **Series updates**: `scripts/update-mainline-kernel.py --check|--update` checks kernel.org, verifies source SHA-256, and tests applying generic + x86 patch stacks with zero fuzz before updating version metadata. Patch review state lives in `configs/mainline-kernel-patches.json` and `docs/mainline-kernel-patch-review.md`.
- **Distribution-style kernel packaging**:
  - `scripts/kernel-package.py` and `package/kernel-bundle` (`scripts/kernel-bundle.py`) package each build `N` into `linux-image-<kver>-N-openwrt` (kernel + all selected `.ko` modules) and `linux-headers-<release>`, plus metapackages `linux-image-openwrt` and `kernel-dev-headers`. `kmod-*` packages contain only autoload/modprobe configs and are kernel-independent.
  - On the router, `/usr/sbin/kernelctl` (`package/custom/openwrt-kernel-upgrade`, state schema 2 in `/etc/openwrt-kernel/`) installs new kernels alongside the running kernel, updates GRUB with a 3-attempt boot counter, blesses healthy boots via `openwrt-kernel-boot.service`, and prunes kernels other than default, fallback, and rescue.
  - Use installation media or offline disk imaging to replace firmware. `sysupgrade` is for configuration archives.

### 3.5 ELF ABI, Signed APKs & Publication Gate
- **ABI scanning**: `scripts/elf-abi.py` generates `/usr/lib/apk/packages/<name>.elf.json` (`so:<SONAME>=0` providers/requires; private loader paths in `configs/elf-abi-policy.json`). `scripts/ucode-abi.py` locks ucode interpreter/module ABI.
- **Rebuild ledger**: `configs/apk-elf-rebuilds.mk` maps exact recipe versions to bumped effective releases for metadata migrations without touching feed recipes.
- **APK immutability and rebuild evidence**: Published APK identities are immutable. Ship changed bytes under a new effective release. `scripts/diagnose-apk-rebuild.py` reports actions such as `reuse_published`, `allocate_release`, and `review_before_allocate`. Both wrappers support `--allocate-rebuilds`. For a digest-bound approval, use `publish-changed-feeds.sh --allocate-rebuilds --approval FILE`. See `docs/apk-rebuild-release.md` for the evidence and preview workflow.
- **Router-gated publication (`scripts/publish-changed-feeds.sh`)**:
  - Publishes to `/srv/openwrt-feeds` (`configs/lan-apk-feeds.json`, served by nginx `lan-apk-feeds.service` for LAN `192.0.2.0/24` and WireGuard `10.0.0.0/24`).
  - Requires a reachable router (`upgrade_preflight.ssh_target`) and reads its APK database under lock. Schema 2 runs one full simulation against both staged views. Legacy schema 1 checks installed kmods for ABI transitions and rejects unfinished kernel trials. A pending APK journal blocks either schema. When a candidate reuses a published generation, the zero-kernel-touch check applies if the router already runs the reused release. See `docs/apk-upgrade-preflight.md`.

- **VM scope**: Routine publication with no major behavior change or new functionality does not require VM validation. Run relevant source/package checks and all coordinated publisher gates; record why VM checks were not run. Major changes and new functionality need relevant runtime validation. The disabled scheduler retains its own exact-image VM gate. See `docs/publication-readiness.md`.
- **Interrupted APK recovery**: APK r18 journals live commits under `/lib/apk/db/transaction/`; `apk-transaction-guard` isolates commits and resumes them at boot with `apk-resume.service`. A pending journal blocks publication and other commits. Never delete it to bypass recovery. See `docs/apk-transaction-recovery.md`.

### 3.6 Router Configuration History (`uci-history`) & Observability (`router-audit`)
- **`uci-history` (`package/custom/uci-history`, `luci-app-uci-history`, `docs/uci-history.md`)**:
  - Versions `/etc/config` and configured `extra_path`s (`/etc/sysupgrade.conf`, `/etc/nftables.d`, `/etc/crontabs`) in a bare Git repo (`/etc/uci-history/repo`, mode 0700) with automatic secret masking and timed rollback transactions (`uci-history-revert-ID.timer` + boot recovery `uci-history-boot.service`).
- **`router-audit` (`package/custom/router-audit`, `docs/router-audit.md`)**:
  - Read-only collector (`router-audit-collect.service`, spool `/srv/router-audit` ≤ 256 MiB / 24h, schema 1.1) and exporter (`/usr/sbin/router-audit-export`). Background collection is **opt-in disabled by default** (`router-audit.main.enabled='0'` since router-audit r6 / daed r10 / dnsmasq r15), while manual exports and historical samples remain available.
  - When enabled, receives nonblocking DNS query metadata (`dns_queries`, `dns_minute`) from `dnsmasq` and `daed` (`ROUTER_AUDIT_DNS=1`), per-flow proxy dial metadata (`conn_flows`) from `daed` (`ROUTER_AUDIT_CONN=1`), and minute conntrack snapshots (`connections`).
  - Companion off-router Debian scripts in `/usr/share/router-audit/`: `pull.py` (SQLite ingestion via restricted `router-audit` SSH account), `analyze.py` (deterministic rates, 7-day baselines, findings, LLM text formatting), `explain.py` (local OpenAI-compatible LLM runner, defaulting to Qwen3.5-4B Q6_K with thinking off), and `mcp_server.py` (read-only stdio MCP server).

### 3.7 Router Datapath & Service Additions
- **Full Cone NAT** (`docs/fullcone-nat.md`): Kernel `CONFIG_NF_NAT_MASQUERADE_FULLCONE`, `libnftnl`/`nftables`/`firewall4` patches, and LuCI checkbox (`0029-luci-firewall-fullcone.patch`), enabled via `firewall.@defaults[0].fullcone='2'`.
- **dnsmasq `nftset` Netlink Fast Path** (`docs/dnsmasq-nftset.md`): Direct netlink insertion for plain IP address sets, falling back to `libnftables`.
- **`daed` eBPF Transparent Proxy** (`package/custom/daed`, `luci-app-daed`, `configs/daed.config`, `docs/daed.md`): Shipped disabled beside default Passwall (init script prevents running both simultaneously); requires kernel BTF (`/sys/kernel/btf/vmlinux`).
- **`ttyd` over HTTPS** (`docs/ttyd-https.md`): Reuses `uhttpd` cert/key when `ssl=1` so LuCI's terminal iframe avoids mixed-content blocking.
- **Unprivileged `pppd`** (`docs/ppp-ujail.md`): Runs in `ujail` as user `ppp` (uid 454) with `CAP_NET_ADMIN`/`CAP_NET_RAW`.
- **LAN Discovery `notrack`** (`docs/lan-discovery-notrack.md`): `firewall4` adds `upnp_ssdp_notrack` (UDP 1900) and `wsd_ipv4_notrack`/`wsd_ipv6_notrack` (UDP 3702) in `notrack_lan`.
- **`irqbalance` Netdev CPU Pools** (`docs/irqbalance-netdev-cpus.md`, feed patch `0038`): Adds repeatable `--netdev-cpus` / UCI `netdev_cpus` rules to pin specified PCI NIC IRQs within a CPU pool.
- **x86 Boot Option (`split_lock_detect=off`)**: Set in `configs/x86-64-systemd-desktop.config` via `CONFIG_GRUB_BOOTOPTS`.
- **Unimplemented Design Studies/Plans**: `docs/resource-governor-plan.md` (approved 2026-11-07 cgroup v2 resource governor design) and `docs/dae-kernel-proxy-study.md` (kernel proxy plane design study) are design records only, not yet built.

---

## 4. Feed & Submodule Structure

- **Independent Feed Repos**: `feeds/packages`, `feeds/luci`, `feeds/video`, `feeds/telephony`, `feeds/passwall_packages`, and `feeds/passwall_luci` are independent Git repositories ignored by the root `.gitignore` but containing live local commits.
  - `patches/feeds/NNNN-<feed>-<topic>.patch` (through `0053-packages-virtio-console-systemd.patch`) and `configs/*-feeds.json` mirror the local commit series for `packages`, `video`, `luci`, and `taskplan`.
  - Never `git reset --hard` or wipe `feeds/` repositories. Do not re-apply `patches/feeds/*` if the feed repo already contains those commits.
- **Submodule**: `package/custom/luci-theme-argon` is a tracked Git submodule (`.gitmodules`, branch `master`). Commits inside it belong to its own repo; the root repo records only the gitlink. (`package/luci-app-argon-config/` is retired and untracked.)
- **Custom Packages (`package/custom/`)**: Linked as the `custom` feed (`src-link custom ../package/custom`). Includes prebuilt binary repacks (`cmake-bin`, `node-bin`, `firefox-esr-bin`, `google-chrome-bin`), glibc compatibility packages, on-device development headers (`native-libs-dev`, `kernel-dev-headers`, `native-build-deps`), X11/Wayland/GNOME/virtualization recipes (`xorg-client.mk`, `xorg-meson.mk`), Rust helpers (`include/rust-*.mk`), and system tools (`openwrt-installer`, `openwrt-kernel-upgrade`, `openwrt-needrestart`, `uci-history`, `router-audit`).

---

## 5. Testing & Validation Conventions

Run the narrowest applicable test suite from the repository root:

```bash
# Host Python unit tests
python3 scripts/tests/test-custom-package-updates.py
python3 scripts/tests/test-elf-abi.py
python3 scripts/tests/test-ucode-abi.py
python3 scripts/tests/test-apk-upgrade-preflight.py
python3 scripts/tests/test-lan-apk-publisher.py
python3 scripts/tests/test-build-and-publish.py
python3 scripts/tests/test-kernel-upgrade.py
python3 scripts/tests/test-mainline-kernel-updates.py
python3 scripts/tests/test-merge-usr.py
python3 scripts/tests/test-network-wait-online.py
python3 scripts/tests/test-systemd-service-bridge.py
python3 scripts/tests/test-systemd-udev-boundary.py
python3 scripts/tests/test-udev-hotplug-migration.py
python3 scripts/audit-hotplug-merge.py
python3 scripts/tests/test-nas-systemd.py
python3 scripts/tests/test-samba4-systemd.py
python3 scripts/tests/test-irqbalance-netdev-cpus.py
python3 scripts/tests/test-uci-history.py
python3 scripts/tests/test-router-audit.py
python3 scripts/tests/test-router-audit-config.py
python3 scripts/tests/test-router-audit-connections.py
python3 scripts/tests/test-openwrt-installer.py

# Host Node.js LuCI view assertions
node scripts/tests/test-luci-needrestart.js
node scripts/tests/test-luci-daed-view.js
node scripts/tests/test-luci-firewall-fullcone.js
node scripts/tests/test-luci-uci-history.js

# Shell & patch checks
sh scripts/tests/test-alternatives.sh
scripts/deptest.sh <package>
scripts/checkpatch.pl <patch>
git diff --check
```

- **VM / Target-only checks**: `scripts/tests/*-guest*.sh|py` (including `nas-systemd-guest.py`, `samba4-systemd-guest.py`, `systemd-service-bridge-guest.py`), `scripts/test-image-network.py`, `scripts/tests/test-daed-vm.py`, `scripts/tests/test-libvirt-secondary-drivers.py` (target-only with `sudo`), and hardware/display probes (`firefox-smoke.sh`, `desktop-kernel-smoke.py`, `sunshine-stream-*`). Always report source checks, disposable VM results, and physical router validation separately.
- **Documentation Pairs**: Every feature pairs `docs/<topic>.md` with a hand-written `docs/<topic>-validation.md` recording the image path, SHA-256, `| Check | Result |` table, explicit scope statement, and external evidence directory (`/srv/openwrt-validation/<topic>-validation-YYYYMMDD/`). Match the language (English for new docs, Chinese for legacy Chinese docs) of neighboring files.

---

## 6. Coding Style, Safety & Operational Guardrails

- **Indentation & Naming**:
  - Use **tabs** in Makefiles, C, shell scripts, and LuCI JS/HTML.
  - Use **4 spaces** in Python.
  - Name patches `NNN-description.patch` and refresh with `make package/<pkg>/refresh` or `make target/linux/refresh` (never `git format-patch`).
  - Use `component: imperative summary` for commit messages and stage explicit file paths.
- **Workspace & Security Guardrails**:
  1. **Scheduled Maintenance is Disabled**: Automatic 72-hour maintenance (`scripts/scheduled-maintenance.py`) was disabled on 2026-10-18. Never reinstall its cron job or run it unless explicitly requested.
  2. **Protect `files/` Overlay**: `.gitignore` ignores `/files`. Only **11 files** under `files/` are tracked (`etc/config/fstab`, `etc/skel/.zshrc`, `etc/ssh/sshd_config.d/00-openwrt-access.conf`, `etc/sudoers.d/10-multiuser`, `etc/uci-defaults/{99-multiuser,99-openssh-access,99-uhttpd-luci,99-zsh-default}`, `etc/zsh/zshrc`, `lib/upgrade/keep.d/{multiuser,openssh-access}`). Never stage or commit personal overlays (`99-zz-desktop-user-user`, credentials, network/DDNS/proxy configs) or root `private-key.pem`/`public-key.pem`.
  3. **Publication vs. Deployment**: Feed publication (`publish-changed-feeds.sh`) and physical device installation are separate operations requiring explicit user authorization.
  4. **Safe Router Configuration (`uci-history`)**: Over SSH, always wrap UCI changes in a timed transaction:
     ```sh
     sudo -n uci-history --json status
     sudo -n uci-history --json begin --timeout 300 --actor agent --note 'purpose'
     # apply authorized changes, verify connectivity and service health
     sudo -n uci-history --json diff
     sudo -n uci-history --json confirm
     ```
     Never include `--show-secrets` output in transcripts, and use existing `sudo -n` root access without modifying sudoers.
