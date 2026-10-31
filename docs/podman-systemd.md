# Desktop-style Podman on the native-systemd image

The x86_64/glibc desktop image builds Podman with the upstream `systemd` Go
tag, builds conmon with `libsystemd` (journald container logs) and installs the
upstream systemd units, Quadlet generator and tmpfiles fragment. crun already
builds with systemd support. This is the same shape a Fedora or Arch desktop
uses: a per-user API socket, socket-activated API service, container restart at
boot, health check timers and journald events. The router-specific rootless
enrollment in [Rootless Podman](podman-rootless.md) is unchanged.

The `systemd` tag changes Podman's runtime defaults. On a native systemd boot
Podman uses the systemd cgroup manager, journald event storage and journald
container logs. Under the GRUB `procd recovery` entry the same binary detects
that systemd is not running and falls back to cgroupfs, file events and
`k8s-file` container logs. Nothing in `/etc/containers/containers.conf`
forces either choice.

## Installed units

The package installs the upstream units under `/usr/lib/systemd/system` and
`/usr/lib/systemd/user`:

| Unit | System | User | Enabled by default |
| --- | --- | --- | --- |
| `podman.socket` | yes | yes | user: `sockets.target.wants` |
| `podman.service` | yes | yes | no (socket-activated) |
| `podman-restart.service` | yes | yes | user: `default.target.wants` |
| `podman-auto-update.service` | yes | yes | no |
| `podman-auto-update.timer` | yes | yes | user: `timers.target.wants` |
| `podman-kube@.service` | yes | yes | no (template) |
| `podman-clean-transient.service` | yes | yes | no |
| `podman-user-wait-network-online.service` | no | yes | pulled by Quadlet units |

`podman-clean-transient.service` is deliberately **not** enabled: it runs
`podman system prune --external` at boot. Enable it manually only if you
understand what it deletes.

The Quadlet generator is installed as:

```text
/usr/lib/systemd/system-generators/podman-system-generator -> ../../podman/quadlet
/usr/lib/systemd/user-generators/podman-user-generator     -> ../../podman/quadlet
```

`/usr/lib/tmpfiles.d/podman.conf` creates and cleans Podman runtime and
temporary directories.

## Rootless operation

The user units are enabled for every account, but rootless Podman still
requires the account to be enrolled with `podman-rootless-setup USER` (see
[Rootless Podman](podman-rootless.md)). The socket lives in the user runtime
directory:

```text
/run/user/<uid>/podman/podman.sock
```

Check and use it as the ordinary user:

```sh
systemctl --user status podman.socket podman-restart.service podman-auto-update.timer
podman info
podman info --format '{{.Host.EventLogger}} {{.Host.LogDriver}} {{.Host.CgroupManager}}'
# journald journald systemd
```

### Compose

`podman compose` uses `docker-compose` as its provider and sets
`DOCKER_HOST` to the rootless socket itself:

```sh
podman compose up -d
podman compose ps
podman compose down
```

The `docker-compose` package is part of the image and does not pull the
Docker CLI. If you invoke `/usr/bin/docker-compose` directly, set the socket
explicitly:

```sh
export DOCKER_HOST="unix://${XDG_RUNTIME_DIR}/podman/podman.sock"
docker-compose up -d
```

The Docker-compatible API is what makes `depends_on: condition:
service_healthy` work with Podman.

### Health checks

Podman creates a transient systemd timer for each container that has a health
check. Via Compose:

```yaml
services:
  db:
    image: docker.io/library/mysql:8.0
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1"]
      interval: 5s
      retries: 20
    restart: unless-stopped
  app:
    image: example/app
    depends_on:
      db:
        condition: service_healthy
```

Inspect the timer and the state:

```sh
podman inspect db --format '{{.State.Health.Status}}'
systemctl --user list-timers --all
```

The timer unit name is derived from the container ID (`<id>[-startup]-<hex>`),
not from a `podman-healthcheck-*` prefix.

### Events and logs

With journald available, `podman events` reads the journal and
`podman logs` reads container journal entries. Event streaming works for
`docker-compose --abort-on-container-exit` and other clients that subscribe
to the API event stream.

### Auto-update

The user timer runs daily. Opt an image in with the standard label:

```sh
podman run -d --label io.containers.autoupdate=registry \
  --name web docker.io/library/nginx:latest
systemctl --user list-timers podman-auto-update.timer
```

The service runs `podman auto-update` and then `podman image prune -f`.

### Quadlet

Quadlet files live under the user's config directory:

```sh
mkdir -p ~/.config/containers/systemd
cat > ~/.config/containers/systemd/web.container <<'EOF'
[Container]
Image=docker.io/library/nginx:latest
PublishPort=8080:80
[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user start web.service
```

### Linger

The user units only start with the user manager. On a headless router, enroll
the account and enable linger so the manager starts at boot:

```sh
# as root
podman-rootless-setup alice
# or, for an already enrolled account
loginctl enable-linger alice
loginctl show-user alice -p Linger
```

`podman-rootless-setup` enables linger for the account it enrolls and prints a
warning if logind is unavailable. Disable it with:

```sh
loginctl disable-linger alice
```

A lingering manager starts `podman.socket`, `podman-restart.service`,
`podman-auto-update.timer` and health check timers without an SSH login.
Containers with `restart: always` / `restart: unless-stopped` are started by
`podman-restart.service`. On native systemd builds, `openwrt-podman-rootless`
installs `podman-rootless-prepare.service` and a `user@.service` drop-in. Each
user manager waits for the system service to load `tun`, check the character
device, and grant enrolled users direct UID ACLs before starting user units.
Pasta drops supplementary groups during isolation, so `root:podman` mode
`0660` alone is insufficient. Updates are locked; unrelated ACLs are retained
and grants managed by this helper are revoked when a user leaves the group.

The dependency uses `Wants` and ordering, rather than requiring success:
a missing module produces an explicit failed preparation unit without blocking
ordinary login. Container startup still fails normally if TUN is unavailable.
`/etc/modules-boot.d/30-podman-tun` and the legacy boot permission hook remain
for procd recovery. Early autoload alone cannot guarantee device and ACL
readiness before lingering user managers, especially with managed kernels.

This barrier covers TUN, not WAN readiness. Quadlets wait for the system
`network-online.target` through `podman-user-wait-network-online.service`; on
this image the target waits for netifd's static local interfaces such as `lan`,
so `Network=pasta:-i,br-lan` containers start after `br-lan` exists. See
[network readiness](systemd.md#network-readiness). The target does not wait for
PPPoE or establish that DNS is usable by default. Applications that need WAN at
startup should retry, or select the upstream interface in that service's drop-in.

## Rootful API (opt-in)

The system units are installed but not enabled. To use the rootful API
(for example, for rootful Compose or a remote Docker client):

```sh
systemctl enable --now podman.socket
systemctl status podman.socket
```

The rootful socket is `/run/podman/podman.sock`. Set `DOCKER_HOST` for
clients that do not accept a socket path directly. The procd init script
`/etc/init.d/podman` is still installed for the recovery boot, but it is a
no-op while systemd is PID 1; it cannot conflict with `podman.socket`.

## procd recovery

Boot the GRUB `(procd recovery)` entry (or pass `openwrt.init=procd`). The
same Podman binary reports `cgroupfs` and file events, because
`/run/systemd/system` is absent. User units and health check timers do not
exist in this mode; `podman` and the rootful API start through
`/etc/init.d/podman start`. Use recovery for firmware operations, not for
running the desktop container stack.

## Upgrade from podman-5.8.4-r4

Older packages installed `events_logger = "none"` and injected
`cgroup_manager = "systemd"` (systemd builds) or `cgroupfs` (procd builds)
into `/etc/containers/containers.conf`. The new package post-install script
removes only those exact lines during an APK upgrade; other user edits are
preserved. A fresh image does not contain them.

If APK leaves a `containers.conf.apk-new`, review it and remove it after the
upgrade; the old file has already been migrated. Reboot (or restart the user
units) after upgrading so the new binary and units are used:

```sh
systemctl --user daemon-reload
systemctl --user restart podman.socket podman-restart.service
```

## Build

```sh
make package/feeds/packages/podman/clean
make package/feeds/packages/podman/compile V=s
make package/feeds/packages/docker-compose/compile V=s
make -j16
```

The native image is written under `bin/systemd`. The feed changes are captured
in `patches/feeds/0013-packages-podman-systemd.patch`; the feed base and
commit are recorded in `configs/podman-systemd-feeds.json`.

See the [2026-10-18 validation record](podman-systemd-validation.md) for the
VM checks, including the Compose health-check reproduction and the procd
recovery comparison.

The TUN startup and D-Bus ownership repair is covered by
[boot readiness validation](boot-readiness-validation.md).
