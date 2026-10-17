# Rootless Podman on the native-systemd image

The x86_64/glibc desktop configuration includes Podman, matching glibc
`shadow-newuidmap` and `shadow-newgidmap` packages, the TUN kernel module,
and `openwrt-podman-rootless`. The UID/GID helpers are root-owned setuid
executables. Native-systemd builds enable crun's systemd support and build
Podman with the upstream `systemd` tag; Podman selects the systemd cgroup
manager and journald at runtime. A procd recovery boot of the same image
falls back to cgroupfs and file events. See
[Desktop-style Podman](podman-systemd.md) for the native units, socket and
linger behavior.

The packaged containers.conf leaves runtime and network directories to
Podman: rootful networks remain under `/etc/containers/networks`, while
rootless networks use the user's storage and runtime data uses
`$XDG_RUNTIME_DIR`. Rootless containers need a PAM/login session and the
systemd user bus. No per-user hardcoded UID or home path is required.

As root, enroll an existing ordinary account:

```sh
podman-rootless-setup alice
```

The helper retains existing subordinate-ID assignments, allocating 65536
IDs when missing without overlapping allocated ranges or real account IDs.
It rejects malformed subordinate-ID files and insufficient existing ranges
for administrator review. Shadow useradd can allocate mappings for new
accounts once the first-boot initialization creates `/etc/subuid` and
`/etc/subgid`. Both files already participate in multiuser sysupgrade
backups. This checkout's personal account initialization also enrolls
`desktop-user`; the package itself creates no ordinary account.

Enrollment adds the account to the `podman` group. A boot service sets
`/dev/net/tun` to `root:podman`, mode 0660. Re-login to refresh supplementary
groups. No systemd-udevd rules are required. If an administrator unloads
and reloads the TUN module, rerun `/etc/init.d/podman-rootless start` to
restore the group policy on the recreated device.

The package also installs `/etc/modules-boot.d/30-podman-tun`. procd's early
kmodloader reads it before handing off to systemd, so `/dev/net/tun` exists
before the lingering user manager and `podman-restart.service` start. Without
it, a boot-time rootless container using slirp4netns can fail with
`open("/dev/net/tun"): No such file or directory`.

On native systemd, enrollment also enables linger for that account:

```sh
loginctl show-user alice -p Linger
# Linger=yes
```

This lets the user manager, `podman.socket`, `podman-restart.service`,
`podman-auto-update.timer` and health check timers run at boot without an
SSH login. `loginctl disable-linger alice` opts the account back out. The
helper prints a warning instead of failing account setup if logind is not
reachable (for example, during a procd recovery boot).

After changing mappings, stop your containers and, as the ordinary user,
run `podman system migrate` to restart Podman's existing rootless namespace.
This stops running containers; schedule it accordingly. Do not use
`podman system reset` to repair a cached path: that deletes containers,
images, volumes and networks. Existing user configs or database paths
from older installations need individual migration and are not silently
rewritten by the package.

Validate from a fresh ordinary-user SSH login:

```sh
podman info
podman unshare cat /proc/self/uid_map /proc/self/gid_map
podman run --rm docker.io/library/alpine:3.23 id
podman run --rm docker.io/library/alpine:3.23 sh -c \
  'nslookup example.com && wget -qO /dev/null https://example.com'
```

Normal startup uses the default network and cgroup settings; it should not
need `--network=host`, `--cgroups=disabled`, a single-ID mapping, or a custom
OCI runtime. Rootless networking uses slirp4netns. DNS/HTTPS success alone
does not establish whether PassWall routed the traffic through a proxy.

The support package changes no firewall or PassWall settings. The upstream
Podman package's existing first-boot firewall integration remains unchanged;
when upgrading an existing router, preserve its UCI files and do not rerun
`90-podman` as part of rootless account enrollment.

Build the narrow packages, then the full image:

```sh
make defconfig
make package/feeds/packages/shadow/compile V=s
make package/feeds/packages/podman/compile V=s
make package/feeds/packages/crun/compile V=s
make package/custom/openwrt-podman-rootless/compile V=s
make -j4 V=s
```

The rootless changes are captured in
`patches/feeds/0007-packages-podman-rootless.patch`; feed base and commit
are recorded in `configs/podman-rootless-feeds.json`. The native
systemd/conmon/compose changes are in
`patches/feeds/0013-packages-podman-systemd.patch`, recorded in
`configs/podman-systemd-feeds.json`. Outputs for native systemd are under
`bin/systemd`; install matching signed glibc APKs when applying this repair
without a router reboot. Flashing the rebuilt image requires a separate
reboot window.

See the [2026-10-13 validation record](podman-rootless-validation.md) for
fresh-image, VM reboot and physical-router results.
