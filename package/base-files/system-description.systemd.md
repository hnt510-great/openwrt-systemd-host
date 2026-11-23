# OpenWrt Systemd Host

This custom x86_64 OpenWrt build combines a router with a general-purpose Linux
host using glibc, signed APK packages and native systemd as PID 1. OpenWrt's
UCI, ubus and netifd manage the router stack; procd remains its service API
while systemd supervises daemons.

## Identity and discovery

- `/etc/os-release` (`/usr/lib/os-release`): `ID=openwrt-systemd`,
  `VARIANT_ID=native-systemd`, `OPENWRT_SYSTEM_DESCRIPTION_FILE` points here.
- `/etc/openwrt_release` and `/etc/openwrt_version`: OpenWrt compatibility
  identity and base-files build revision.
- Recorded image capabilities (`OPENWRT_FEATURES`): **@OPENWRT_FEATURES@**.

Metadata reflects build or deployment state, not live services, later APK
changes or the currently booted kernel. Query the live system before acting:

```sh
cat /etc/os-release /etc/openwrt_release
uname -r; cat /proc/1/comm
ubus call system board
kernelctl list
systemctl --no-pager list-units 'openwrt-*@*.service'
findmnt /overlay /boot
```

## Services and networking

- **PID 1 & logs**: systemd is the sole normal PID 1 (`systemctl`,
  `journalctl`). Service output goes to the journal; `logread` and LuCI System
  Log expose a compatibility view. systemd owns the hardware watchdog
  (`RuntimeWatchdogSec=30s`).
- **Router services**: `openwrt-procd.service` (`procd --systemd=units`) turns
  init-script instances into transient `openwrt-SERVICE@INSTANCE.service` units
  under `openwrt-SERVICE.slice` (falling back to `openwrt-*.scope` for vrf,
  trace, bundle or fd-passing). Control them via `/etc/init.d/NAME`,
  `systemctl <action> openwrt@NAME.service` (CLI bridge), LuCI or `ubus`. PID 1
  refuses direct start/stop/restart/reload on transient procd units.
- **Native units**: `sshd.service` and `dbus.service` run natively; NAS services
  (`samba4`, `wsdd2`, `avahi-daemon`) run in `nas.slice`; auxiliary services
  (`cron`, `nlbwmon`, `ddns-go`) run in `auxiliary.slice`.
- **Networking**: `netifd` owns interfaces (`uci show network`,
  `ubus call network.interface dump`); `systemd-networkd` and `systemd-resolved`
  are disabled. `openwrt-network-wait-online.service` holds
  `network-online.target` until autostart static local interfaces (e.g. `lan`)
  are up, timing out after 120s (WAN/PPPoE/VPN outages do not block it).

## Configuration history and audit

- **`uci-history`**: versions `/etc/config` and configured extra paths with
  masked secrets (LuCI *System → Configuration History*; agent guide:
  `/usr/share/doc/uci-history/AGENT-GUIDE.md`). Wrap remote/UCI edits in a timed
  transaction (**begin → change → verify → confirm**): unconfirmed changes
  auto-revert on timer expiry or next boot. Use `sudo -n`, avoid LuCI apply
  while a CLI transaction is armed, and never log `--show-secrets`.

  ```sh
  sudo -n uci-history --json status
  sudo -n uci-history --json begin --timeout 300 --actor agent --note 'purpose'
  # apply, commit, reload and verify changes
  sudo -n uci-history --json diff
  sudo -n uci-history --json confirm   # or: abort
  ```

- **`router-audit`**: opt-in (`router-audit.main.enabled='0'` by default). When
  enabled, `router-audit-collect.service` writes read-only snapshots, minute
  samples, DNS query metadata and connection flows to root-only
  `/srv/router-audit` (≤ 256 MiB / 24h). Query with `router-audit-export
  capabilities|snapshot|incidents|dns`; off-router analysis scripts live in
  `/usr/share/router-audit/` (guide: `/usr/share/doc/router-audit/README.md`).
  Keep audit data inside the local environment.

## Router additions

Inspect UCI and the running kernel before assuming optional features are active:

- **Full cone NAT**: `firewall.@defaults[0].fullcone='2'` + `fw4 reload` enables
  IPv4 UDP full-cone masquerading (needs `CONFIG_NF_NAT_MASQUERADE_FULLCONE`;
  `srcnat_wan` shows `masquerade fullcone`).
- **dnsmasq nftset**: automatic netlink fast path for plain IP sets, falling
  back to libnftables.
- **daed**: eBPF transparent proxy, disabled by default and mutually exclusive
  with Passwall. Dashboard listens on port 2023 (LAN/WireGuard only; state in
  `/etc/daed/wing.db`); requires `/sys/kernel/btf/vmlinux`.
- **ttyd**: port 7681; reuses uhttpd's certificate/key when `ssl=1`.
- **PPP**: `pppd` and `/etc/ppp/ip-{up,down}.d` hooks run in ujail as user `ppp`
  (uid 454) with `CAP_NET_ADMIN`/`CAP_NET_RAW`.
- **LAN discovery notrack**: `notrack_lan` skips conntrack for SSDP (UDP 1900)
  and WS-Discovery (UDP 3702).
- **Wireless AP**: onboard Intel AX101 (`phy0-ap0`, bridged into `br-lan`,
  `/etc/config/wireless`) supports 2.4 GHz AP mode only (self-managed firmware
  marks 5 GHz no-IR).
- **irqbalance**: optional `list netdev_cpus 'IFACE:CPULIST'` in
  `/etc/config/irqbalance` restricts matching PCI NIC IRQs to a CPU pool.

## Optional capabilities

`OPENWRT_FEATURES` values: `desktop` (GNOME Wayland), `virtualization`
(libvirt/QEMU), `flatpak`, `containers` (Podman), `appimage`, `distrobox`,
`native-development` (GCC/headers).

### Desktop, audio and IME

- **GNOME session & RDP**: runs as an ordinary user (`openwrt-desktop.service`,
  configured via `desktop-setup USER` and `/etc/config/desktop`). GNOME Remote
  Desktop shares that same session over LAN IPv4 TCP 3389 (`desktop-rdp-setup
  USER`; no VNC/xrdp). Keyring bootstrap credentials live under root-only
  `/etc/desktop/gnome/` (TPM2-sealed when available)—preserve user keyrings,
  bootstrap creds and RDP TLS identity across upgrades.
- **Apps**: Nautilus, GNOME Terminal, Settings (router networking remains in
  LuCI/UCI), Tweaks, Firefox ESR and `google-chrome-bin` (Wayland, updated via
  APK).
- **Audio & streaming**: `desktop-audio-setup USER` enrolls PipeWire/WirePlumber
  (`wpctl status`, `pactl info`). `sunshine-setup USER
  --capture=portal|--enable-kms` configures Sunshine/Moonlight.
- **Scheduling**: RealtimeKit (`rtkit-daemon.service`) grants priority to Mutter
  and PipeWire (`kms_scheduling` in `/etc/config/desktop`; kernel built with
  `PREEMPT_DYNAMIC`, `HZ=1000`, `RT_GROUP_SCHED_DEFAULT_DISABLED`).
- **IME (`openwrt-desktop-ime`)**: Fcitx5 (IBus compat, Kimpanel, GTK/Qt
  modules) with offline Chinese Pinyin; **Ctrl+Space** toggles on fresh
  profiles.
- Run `systemctl --user`, `wpctl`, `flatpak` and desktop commands in the
  ordinary user's session, not root's.

### Virtualization, containers and development

- **Libvirt/QEMU** (`qemu:///system`): KVM, OVMF/Secure Boot, emulated TPM 2.0
  (`swtpm`, state under `/srv/libvirt/state`), PCI/USB passthrough (check
  `virt-host-validate qemu`; never pass through a router NIC) and `virtio-fs`
  (`/srv/libvirt/shares`). Guests attach to OpenWrt bridges (`br-lan`; `virbr*`
  is not built). Restarting `virtqemud` does not stop guests.
- **Containers & apps**: Podman (rootful and rootless with systemd/Quadlets),
  Distrobox, Flatpak (per-user and `flatpak-system-helper.service` authorized by
  polkit/`sudo` group) and AppImage.
- **Native development**: GCC, native headers/pkg-config and
  `kernel-dev-headers` (`/usr/lib/modules/<release>/build`).

## Packages, kernels and recovery

- **APK & LAN feed**: `lan-apk-feeds` configures signed repositories at
  `http://apk.example.invalid:8088` (not interchangeable with upstream snapshots).
  Preview upgrades with `apk upgrade --simulate` (or `--userspace-only
  --simulate`). Upgrades only start enabled services.
- **Transaction recovery**: started APK commits defer Ctrl-C/SIGTERM/HUP;
  `apk-transaction-guard` isolates commits from caller restarts and shutdowns.
  Interrupted commits journal in `/lib/apk/db/transaction/` and resume on next
  boot via `apk-resume.service` (`apk-resume --status`; never delete the
  journal).
- **Parallel kernels (`openwrt-kernel-upgrade`)**: each `linux-image-<release>`
  carries its own modules (`kmod-*` is autoload-only). `apk upgrade` installs
  new kernels alongside the running one with a 3-attempt GRUB boot counter and
  automatic fallback. Manage with `kernelctl list|status|set-default|rollback|remove`
  (keeps default, fallback and rescue).
- **Restart advice**: `needrestart --cached --json` or LuCI *Restart Needed*
  (advisory only; does not restart workloads).
- **Firmware, failsafe & installer**: `sysupgrade` (`-b`, `-l`, `-r`) is for
  configuration backup/restore only; replace firmware via offline disk imaging
  or the hybrid BIOS/UEFI whole-disk installer ISO (GPT: ESP, read-only rootfs,
  ext4/btrfs/xfs overlay; excludes untracked personal overlays). The GRUB
  failsafe entry boots native OpenWrt preinit (`mount_root`).
