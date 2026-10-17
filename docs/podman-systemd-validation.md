# Desktop-style Podman validation, 2026-10-18

The x86_64/glibc native-systemd image was rebuilt from this checkout and booted
in a disposable KVM/UEFI VM. No physical router was flashed and no packages
were published.

| Package | Version |
| --- | --- |
| podman | 5.8.4-r5 |
| conmon | 2.2.1-r3 |
| docker-compose | 5.6.0-r2 |
| crun | 1.28-r2 |
| libsystemd | 262-r3 |
| openwrt-podman-rootless | 2 |
| kernel | 6.18.55~1e6d3a41204c57acfef0c7a584b7cc0e-r1 (generation g17) |

Image:
`bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`

SHA256:
`a166a38e9773d9325e66303441d70b8d6d6fc149c7422d343684c1bc9f721f07`

## Build

The full image was built with:

```sh
make CONFIG_OPENWRT_KERNEL_SEQUENCE=17 -j16 V=s
```

The workspace's compiled kernel was generation g17 while `.config` carried
`CONFIG_OPENWRT_KERNEL_SEQUENCE=16`; the explicit override selected the existing
matching kernel generation and avoided an unrelated kernel rebuild. The Podman,
conmon and docker-compose changes are userspace-only.

The Podman compile used
`-tags "seccomp exclude_graphdriver_devicemapper apparmor systemd"` and emitted
no "compiled without the systemd build tag" warning. The APK contains both
system and user unit trees, the Quadlet generator symlinks and
`/usr/lib/tmpfiles.d/podman.conf`. `conmon` was rebuilt with meson finding
libsystemd 262 and links `libsystemd.so.0`. `docker-compose` no longer depends
on the Docker CLI.

The feed changes are in
`patches/feeds/0013-packages-podman-systemd.patch`, from feed base
`454b8c82dd468b3896bcabe50d34871f7614b103` to local commit
`ad79cb8b4cad6a77b8d9449a2f6704c1768d6242`, recorded in
`configs/podman-systemd-feeds.json`.

## VM results

The guest booted from the image above, created the ordinary account, enrolled
it with `podman-rootless-setup` (including linger) and loaded an offline Alpine
3.23 image from a separate ext4 disk. The full smoke script ran as that account.

| Check | Result |
| --- | --- |
| System and user Podman units, generator links and tmpfiles installed | pass |
| System-side units disabled by default | pass |
| Rootful `podman info`: `journald journald systemd` | pass |
| `loginctl` linger and user bus for the ordinary account | pass |
| Rootless socket and `podman info`: `journald journald systemd` | pass |
| Compose with `depends_on: condition: service_healthy` | pass |
| Transient container-ID healthcheck timer | pass |
| `podman events` (journald backend) | pass |
| Direct `docker-compose` over the rootless Podman API | pass |
| Quadlet user service from `~/.config/containers/systemd` | pass |
| `restart: unless-stopped` container restarted after a reboot | pass (`boot-test` up, `podman-restart.service` active) |
| Old `events_logger = "none"` / `cgroup_manager = "systemd"` conffile migration | pass (`MIGRATION_OK`) |
| procd recovery: PID 1 is procd, `cgroupfs file`, rootful API socket | pass |

The healthcheck-gated Compose stack is the audit's failing case:
`podman compose up -d` with a database healthcheck and an application
`depends_on: service_healthy` now starts both services. The transient timer is
named from the container ID, as upstream Podman 5.8 does.

The reboot check created a rootless container on the default slirp4netns
network and rebooted the VM. `podman-restart.service` started it without a
login because linger was enabled. This also exercises the early
`/etc/modules-boot.d/30-podman-tun` autoload: without it, slirp4netns fails
with `open("/dev/net/tun"): No such file or directory` when the user manager
starts before the OpenWrt boot module loader.

## procd recovery

The procd check used a direct kernel boot of the same image with
`openwrt.init=procd`, because the image's 2-second GRUB timeout makes automated
menu selection unreliable. The guest reported:

```text
procd
PROCD_MODE
cgroupfs file
srw------- 1 root root 0 /run/podman/podman.sock
CONTAINER ID  IMAGE  COMMAND  CREATED  STATUS  PORTS  NAMES
```

`/etc/init.d/podman start` still starts the rootful API, and the rootless
healthcheck timers and user units are absent in this mode. This is the
documented recovery behavior.

## Scope

- The VM was disposable; the physical router at `192.0.2.1` was not flashed,
  rebooted or modified.
- The test VM had no external network. The Alpine image was loaded from an
  offline docker-archive on an ext4 disk because the kernel does not build the
  virtio 9p transport.
- Rootful remote clients, registry auto-update traffic, physical NICs, Wi-Fi
  and PPPoE were not exercised.
- The image's GRUB timeout is part of the existing configuration; the procd
  check booted the same kernel and root filesystem directly rather than
  changing the menu timeout for the validation.

Evidence, including the VM driver log, serial logs and the offline image, is in
`/srv/openwrt-validation/podman-systemd-validation-20261018/`.
