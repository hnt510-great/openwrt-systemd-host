# GEMINI.md

This file provides project memory, architectural context, and operational rules for Gemini / Antigravity when working in this repository.

---

## 1. Project Overview & Core Divergences

This repository is a heavily customized OpenWrt fork tracking `openwrt/openwrt` `main` (~300 commits ahead). It targets `x86/64` as a combined **router plus general-purpose Linux desktop/virtualization/container host** built on foundations that differ from stock OpenWrt:

- **C Library (`glibc`)**: Uses `glibc` instead of `musl` (`CONFIG_LIBC_USE_GLIBC=y`, `CONFIG_USE_GLIBC=y`), with Debian multiarch compatibility (`/lib/x86_64-linux-gnu`, `/usr/lib/x86_64-linux-gnu`) via `glibc-distro-compat`.
- **Package Manager (`APK`)**: Uses signed APK packages (`CONFIG_USE_APK=y`, `CONFIG_SIGNED_PACKAGES=y`) with explicit ELF SONAME (`so:<SONAME>=0`) and ucode ABI contracts instead of `opkg`.
- **Init & Supervision (`native systemd` + `procd`)**: Runs native `systemd` as PID 1 (`CONFIG_OPENWRT_SYSTEMD=y`) with a merged `/usr` filesystem (`scripts/merge-usr.py`), while retaining `procd` as the OpenWrt ubus/hotplug/rc service API and as a GRUB recovery init (`openwrt.init=procd`).
- **Kernel (`Mainline Linux 7.3`)**: Target `x86/64` runs mainline Linux 7.3 (`CONFIG_LINUX_7_3=y`, currently 7.3.x); `6.18` kernel configs/patches are retained alongside it. Kernels ship as parallel, ABI-pinned distribution packages (`linux-image-<kver>-<gen>-openwrt`) managed on-device by `kernelctl`.
- **Desktop Session (`GNOME 51`)**: Shared-user GNOME Wayland desktop on VT7 (`package/custom/openwrt-desktop`) started via PAM/logind without a display manager, shared over LAN IPv4 RDP (`gnome-remote-desktop`) and Sunshine/Moonlight, with Fcitx5 (`openwrt-desktop-ime`) and PipeWire (`openwrt-desktop-audio`).
- **Core Build-System Surgery**: Directly modifies upstream build and core files (`include/kernel.mk`, `include/package-pack.mk`, `include/package.mk`, `include/rootfs.mk`, `package/base-files`, `package/system/{apk,procd,systemd}`, `package/network/{services/dnsmasq,utils/nftables,config/firewall4}`, `package/libs/libnftnl`, `target/linux/x86/image`).

Build outputs:
- **Native systemd firmware & APK feeds**: `bin/systemd/` (e.g., `bin/systemd/targets/x86/64-glibc/`).
- **Stock images**: `bin/targets/`.

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
- **Full Snapshot**: `configs/x86-64-systemd-desktop.config` (~381 KB) is the complete accepted configuration snapshot (`cp configs/x86-64-systemd-desktop.config .config && make defconfig`).
- Do **not** rely on `scripts/diffconfig.sh` to minimize `.config`; circular Kconfig dependencies (`video-support`, `openwrt-desktop`, `glib2-gir`, Mesa) break minimization.

### Building & Patch Refreshing
```bash
make -j3 V=s                                              # Build configured firmware (plain make does NOT reserve a kernel generation)
make package/custom/<name>/compile V=s                    # Build a single custom package
make target/linux/compile V=s                             # Build kernel only
make package/<name>/prepare V=s                           # Unpack and apply patches for a package
make package/<name>/refresh V=s                           # Regenerate quilt patches for a package
make target/linux/refresh V=s                             # Regenerate quilt patches for the kernel
python3 scripts/build-and-publish.py build-only -j12 V=s  # Full build reserving a kernel generation without publishing
```

### Publication & Kernel Maintenance
```bash
./scripts/build-and-publish.sh -j16                       # Build + preflight + publish userspace APKs and kernel generation
./scripts/publish-changed-feeds.sh [--dry-run]            # Run live-router preflight simulation, then publish changed APKs
python3 scripts/update-mainline-kernel.py --check|--update # Compare Linux 7.3 series against kernel.org / update point release
```

---

## 3. Architecture & Subsystems

### 3.1 Dual-Init & Native Systemd Supervision
- **Boot path**: `/sbin/init` mounts early filesystems, runs preinit, and mounts overlayfs. GRUB default passes `openwrt.init=systemd` to exec `systemd` as PID 1 (falling back to `procd` if preflight fails); the `procd recovery` GRUB entry passes `openwrt.init=procd`.
- **Integration (`package/system/systemd-openwrt/`)**:
  - `openwrt-ubusd.service`: Runs `ubusd`.
  - `openwrt-procd.service`: Runs `procd --systemd=units`. `procd` remains the ubus service/system/hotplug API and runs `/etc/hotplug.d` and `/etc/rc.button` handlers fed by `systemd-udevd`, while each normal service instance registered via `procd.sh` becomes a transient `openwrt-SERVICE@INSTANCE.service` under `openwrt-SERVICE.slice` (procd patch `130-systemd-transient-units.patch`). Instances requiring `vrf`, `trace`, `bundle`, or descriptor passing fall back to procd children in `openwrt-*.scope`.
  - `openwrt-services.service`: Runs enabled `/etc/init.d/*` rc scripts in sequence.
  - `openwrt-network-wait-online.service`: Holds `network-online.target` until `netifd` brings up autostart static local interfaces (e.g., `lan`), up to 120s.
- **CLI Service Bridge (`package/system/systemd-openwrt-services/`)**:
  - Maps `systemctl start|stop|restart|reload|enable|status openwrt@NAME.service` onto `/etc/init.d/NAME` (`dbus` and `sshd` use native units). PID 1 refuses direct start/stop/restart/reload jobs on transient `openwrt-SERVICE@INSTANCE.service` units from non-procd clients so init script hooks are not bypassed.
- **Merged `/usr` (`scripts/merge-usr.py`)**:
  - Invoked from `include/package-pack.mk` and `include/rootfs.mk` to rewrite `/bin`, `/sbin`, `/lib` into `/usr/...`. `ALTERNATIVE_COMMANDS` handles BusyBox applet collisions (`dmesg`, `mount`, `passwd`, `ping`, `reboot`, etc.).

### 3.2 Whole-Disk USB & Optical Installer ISO
- Enabled via `configs/installer-iso.config` (`CONFIG_INSTALLER_ISO_IMAGES`), producing `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-installer.iso`.
- Built from `TARGET_DIR_ORIG` plus **only git-tracked `files/` defaults** (personal untracked overlays in `files/` are excluded).
- Boots via hybrid BIOS/UEFI from raw USB (partition 3) or optical/virtual SATA CD-ROM (external initramfs loop-mounts the appended squashfs read-only) with `fstools_overlay=tmpfs` into an English whiptail TUI (`package/custom/openwrt-installer`, supports `openwrt-installer --answers FILE [--dry-run]`).
- Creates a fresh GPT (p128 BIOS gap, p1 FAT32 ESP `/boot`, p2 read-only `rootfs` squashfs, p3 `rootfs_data` overlay with `ext4`/`btrfs`/`xfs`, optional p4+ data partitions), configures LAN/WAN/firewall/accounts, and schedules a firstboot unit for optional regular user + `desktop-setup`. See `docs/installer-iso.md`.

### 3.3 GNOME 51 Desktop, Audio, IME & Remote Access
- **Meta-packages**: `openwrt-desktop`, `openwrt-desktop-ime` (Fcitx5 + Kimpanel + Pinyin/libime + CJK fonts), `openwrt-desktop-audio` (PipeWire + WirePlumber + PulseAudio compat).
- **Session model**: Runs as an ordinary user on VT7 via PAM/logind (`openwrt-desktop.service`). Shares the same local Wayland display over RDP (`gnome-remote-desktop` bound to LAN IPv4 TCP 3389) and Sunshine/Moonlight. Keyring bootstrap secrets live under root-only `/etc/desktop/gnome/` passed via systemd `LoadCredential`.
- **On-device provisioning commands (run as root)**:
  ```sh
  desktop-setup USER
  desktop-rdp-setup USER [--password-stdin]
  sunshine-setup USER --capture=portal|--enable-kms
  desktop-audio-setup USER
  ```
- See `docs/gnome-desktop.md`.

### 3.4 Mainline Kernel & Parallel Generations
- **Series updates**: `scripts/update-mainline-kernel.py --check|--update` checks kernel.org, verifies source SHA-256, and tests applying generic + x86 patch stacks with zero fuzz before updating version metadata. Patch review state lives in `configs/mainline-kernel-patches.json` and `docs/mainline-kernel-patch-review.md`.
- **Distribution-style kernel packaging**:
  - `scripts/kernel-package.py` and `package/kernel-bundle` (`scripts/kernel-bundle.py`) package each build `N` into `linux-image-<kver>-N-openwrt` (kernel + all selected `.ko` modules) and `linux-headers-<release>`, plus metapackages `linux-image-openwrt` and `kernel-dev-headers`. `kmod-*` packages contain only autoload/modprobe configs and are kernel-independent.
  - On the router, `/usr/sbin/kernelctl` (`package/custom/openwrt-kernel-upgrade`, state schema 2 in `/etc/openwrt-kernel/`) installs new kernels alongside the running kernel, updates GRUB with a 3-attempt boot counter, blesses healthy boots via `openwrt-kernel-boot.service`, and prunes kernels other than default, fallback, and rescue.
  - Firmware flashing via `sysupgrade` is blocked under native systemd; boot the GRUB **procd recovery** entry to flash full images.

### 3.5 ELF ABI, Signed APKs & Publication Gate
- **ABI scanning**: `scripts/elf-abi.py` generates `/usr/lib/apk/packages/<name>.elf.json` (`so:<SONAME>=0` providers/requires; private loader paths in `configs/elf-abi-policy.json`). `scripts/ucode-abi.py` locks ucode interpreter/module ABI.
- **Rebuild ledger**: `configs/apk-elf-rebuilds.mk` maps exact recipe versions to bumped effective releases for metadata migrations without touching feed recipes.
- **Immutability**: Published APK package identities are immutable—any byte change requires bumping `PKG_RELEASE`. When a same-version rebuild differs, `scripts/diagnose-apk-rebuild.py` classifies differences as `benign`, `change`, or `unknown`.
- **Router-gated publication (`scripts/publish-changed-feeds.sh`)**:
  - Publishes to `/srv/openwrt-feeds` (`configs/lan-apk-feeds.json`, served by nginx `lan-apk-feeds.service` for LAN (`192.0.2.0/24`) and WireGuard (`10.0.0.0/24`)).
  - Requires a reachable live router (`upgrade_preflight.ssh_target`, `router-admin@192.0.2.1` (empty in public example)), reads its APK database under lock, checks installed kmods against candidate kernel ABI, and runs `scripts/apk-upgrade-preflight.py` (`--plan-json`, `--userspace-only`) before exposing snapshots. Never pushes packages directly onto the router.

### 3.6 Router Configuration History (`uci-history`) & Observability (`router-audit`)
- **`uci-history` (`package/custom/uci-history`, `luci-app-uci-history`, `docs/uci-history.md`)**:
  - Versions `/etc/config` and configured `extra_path`s (`/etc/sysupgrade.conf`, `/etc/nftables.d`, `/etc/crontabs`) in a bare Git repo (`/etc/uci-history/repo`, mode 0700) with automatic secret masking and timed rollback transactions (`uci-history-revert-ID.timer` + boot recovery `uci-history-boot.service`).
- **`router-audit` (`package/custom/router-audit`, `docs/router-audit.md`, `docs/router-audit-debian.md`)**:
  - Read-only collector (`router-audit-collect.service`, spool `/srv/router-audit` ≤ 256 MiB / 24h, schema 1.1) and exporter (`/usr/sbin/router-audit-export`).
  - Receives nonblocking DNS query metadata (`dns_queries`, `dns_minute`) from `dnsmasq` and `daed` (`ROUTER_AUDIT_DNS=1`), per-flow proxy dial metadata (`conn_flows`) from `daed` (`ROUTER_AUDIT_CONN=1`), and minute conntrack snapshots (`connections`).
  - Companion off-router Debian scripts in `/usr/share/router-audit/`: `pull.py` (SQLite ingestion via restricted `router-audit` SSH account), `analyze.py` (deterministic rates, 7-day baselines, findings, LLM text formatting), `explain.py` (local OpenAI-compatible LLM runner, defaulting to Qwen3.5-4B Q6_K with thinking off), and `mcp_server.py` (read-only stdio MCP server).

### 3.7 Router Datapath & Service Additions
- **Full Cone NAT** (`docs/fullcone-nat.md`): Kernel `CONFIG_NF_NAT_MASQUERADE_FULLCONE`, `libnftnl`/`nftables`/`firewall4` patches, and LuCI checkbox (`0029-luci-firewall-fullcone.patch`), enabled via `firewall.@defaults[0].fullcone='2'`.
- **dnsmasq `nftset` Netlink Fast Path** (`docs/dnsmasq-nftset.md`): Direct netlink insertion for plain IP address sets, falling back to `libnftables`.
- **`daed` eBPF Transparent Proxy** (`package/custom/daed`, `luci-app-daed`, `configs/daed.config`, `docs/daed.md`): Shipped disabled beside default Passwall (init script prevents running both simultaneously); requires kernel BTF (`/sys/kernel/btf/vmlinux`).
- **`ttyd` over HTTPS** (`docs/ttyd-https.md`): Reuses `uhttpd` cert/key when `ssl=1` so LuCI's terminal iframe avoids mixed-content blocking.
- **Unprivileged `pppd`** (`docs/ppp-ujail.md`): Runs in `ujail` as user `ppp` (uid 454) with `CAP_NET_ADMIN`/`CAP_NET_RAW`.
- **LAN Discovery `notrack`** (`docs/lan-discovery-notrack.md`): `firewall4` adds `upnp_ssdp_notrack` (UDP 1900) and `wsd_ipv4_notrack`/`wsd_ipv6_notrack` (UDP 3702) in `notrack_lan`.
- **Resource Governor Plan** (`docs/resource-governor-plan.md`): Approved staged design (2026-11-07, not yet built) for router-first cgroup v2 resource policy (`openwrt-resource-policy` static policy `S`, optional `resgovd` adaptive governor `A`, and `scripts/resbench/` A/B harness).

---

## 4. Feed & Submodule Structure

- **Independent Feed Repos**: `feeds/packages`, `feeds/luci`, `feeds/video`, `feeds/telephony`, `feeds/passwall_packages`, and `feeds/passwall_luci` are independent Git repositories ignored by the root `.gitignore` but containing live local commits.
  - `patches/feeds/NNNN-<feed>-<topic>.patch` and `configs/*-feeds.json` mirror the local commit series for `packages`, `video`, and `luci`.
  - Never `git reset --hard` or wipe `feeds/` repositories. Do not re-apply `patches/feeds/*` if the feed repo already contains those commits.
- **Submodule**: `package/custom/luci-theme-argon` is a tracked Git submodule (`.gitmodules`, branch `master`). Commits inside it belong to its own repo; the root repo records only the gitlink. (`package/luci-app-argon-config/` is retired and untracked.)
- **Custom Packages (`package/custom/`)**: Linked as the `custom` feed (`src-link custom ../package/custom`). Includes prebuilt binary repacks (`cmake-bin`, `node-bin`, `firefox-esr-bin`), glibc compatibility packages, on-device development headers (`native-libs-dev`, `kernel-dev-headers`, `native-build-deps`), X11/Wayland/GNOME/virtualization recipes (`xorg-client.mk`, `xorg-meson.mk`), Rust helpers (`include/rust-*.mk`), and system tools (`openwrt-installer`, `openwrt-kernel-upgrade`, `openwrt-needrestart`, `uci-history`, `router-audit`).

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
python3 scripts/tests/test-uci-history.py
python3 scripts/tests/test-router-audit.py
python3 scripts/tests/test-router-audit-analysis.py
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

- **VM / Target-only checks**: `scripts/tests/*-guest*.sh|py`, `scripts/test-image-network.py`, `scripts/tests/test-daed-vm.py`, `scripts/tests/test-libvirt-secondary-drivers.py` (target-only with `sudo`), and hardware/display probes (`firefox-smoke.sh`, `desktop-kernel-smoke.py`, `sunshine-stream-*`). Always report source checks, disposable VM results, and physical router validation separately.
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
  2. **Protect `files/` Overlay**: `.gitignore` ignores `/files`. Only **11 files** under `files/` are tracked (`etc/config/fstab`, `etc/skel/.zshrc`, `etc/ssh/sshd_config.d/00-openwrt-access.conf`, `etc/sudoers.d/10-multiuser`, `etc/uci-defaults/{99-multiuser,99-openssh-access,99-uhttpd-luci,99-zsh-default}`, `etc/zsh/zshrc`, `lib/upgrade/keep.d/{multiuser,openssh-access}`). Never stage or commit personal overlays (`99-zz-user`, credentials, network/DDNS/proxy configs) or root `private-key.pem`/`public-key.pem`.
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
