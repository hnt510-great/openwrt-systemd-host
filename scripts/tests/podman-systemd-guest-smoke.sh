#!/bin/sh
# Run as root on a native-systemd guest created from the desktop image.
# Usage: podman-systemd-guest-smoke.sh [ordinary-user] [image]
# The image must already be present in the ordinary user's Podman storage
# (for example, loaded from an offline docker-archive via the 9p share).
set -eu

[ "$(id -u)" = 0 ] || { echo 'run as root' >&2; exit 1; }
[ "$(cat /proc/1/comm)" = systemd ] || { echo 'systemd is not PID 1' >&2; exit 1; }
user=${1:-}
image=${2:-docker.io/library/alpine:3.23}

pass() { printf 'ok - %s\n' "$*"; }
fail() { printf 'FAIL - %s\n' "$*" >&2; exit 1; }

# --- packaged payload -------------------------------------------------------
for unit in podman.service podman.socket podman-restart.service \
	podman-auto-update.service podman-auto-update.timer \
	podman-kube@.service podman-clean-transient.service; do
	[ -f "/usr/lib/systemd/system/$unit" ] || fail "missing system unit $unit"
	[ -f "/usr/lib/systemd/user/$unit" ] || fail "missing user unit $unit"
done
[ -f /usr/lib/systemd/user/podman-user-wait-network-online.service ] ||
	fail 'missing podman-user-wait-network-online.service'
[ -x /usr/lib/podman/quadlet ] || fail 'missing /usr/lib/podman/quadlet'
[ "$(readlink -f /usr/lib/systemd/system-generators/podman-system-generator)" = \
	/usr/lib/podman/quadlet ] || fail 'bad podman-system-generator link'
[ "$(readlink -f /usr/lib/systemd/user-generators/podman-user-generator)" = \
	/usr/lib/podman/quadlet ] || fail 'bad podman-user-generator link'
[ -f /usr/lib/tmpfiles.d/podman.conf ] || fail 'missing podman tmpfiles entry'
for link in \
	/usr/lib/systemd/user/sockets.target.wants/podman.socket \
	/usr/lib/systemd/user/default.target.wants/podman-restart.service \
	/usr/lib/systemd/user/timers.target.wants/podman-auto-update.timer; do
	[ -L "$link" ] || fail "missing user enablement link $link"
done
[ ! -e /usr/lib/systemd/user/default.target.wants/podman-clean-transient.service ] ||
	fail 'podman-clean-transient must not be enabled'
if systemctl is-enabled --quiet podman.socket; then
	fail 'system podman.socket is enabled'
fi
pass 'systemd payload and user enablement'

# --- rootful runtime --------------------------------------------------------
root_info=$(podman info --format '{{.Host.EventLogger}} {{.Host.LogDriver}} {{.Host.CgroupManager}}')
[ "$root_info" = 'journald journald systemd' ] ||
	fail "rootful podman info: $root_info"
pass 'rootful journald/systemd defaults'

[ -n "$user" ] || { echo 'no ordinary user requested; root checks complete'; exit 0; }
id "$user" >/dev/null 2>&1 || fail "no such user: $user"
uid=$(id -u "$user")
home=$(getent passwd "$user" | cut -d: -f6)
[ "$uid" -ge 1000 ] || fail "$user is not an ordinary account"
[ "$(loginctl show-user "$user" -p Linger --value)" = yes ] ||
	fail "linger is not enabled for $user"
[ -S "/run/user/$uid/bus" ] || fail "user bus is missing for $user"
pass 'linger and user bus'

run_user() {
	su -s /bin/sh "$user" -c \
		"export HOME='$home' XDG_RUNTIME_DIR='/run/user/$uid' DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/$uid/bus'; $*"
}

for unit in podman.socket podman-restart.service podman-auto-update.timer; do
	run_user "systemctl --user is-active --quiet $unit" ||
		fail "$unit is not active"
done
[ -S "/run/user/$uid/podman/podman.sock" ] || fail 'rootless podman socket is missing'
user_info=$(run_user "podman info --format '{{.Host.EventLogger}} {{.Host.LogDriver}} {{.Host.CgroupManager}}'")
[ "$user_info" = 'journald journald systemd' ] ||
	fail "rootless podman info: $user_info"
pass 'rootless socket and journald/systemd defaults'

# --- healthcheck-gated compose ---------------------------------------------
work=$(mktemp -d)
trap 'rm -rf "$work"; [ -n "${compose_started:-}" ] && run_user "cd $work && podman compose down" >/dev/null 2>&1 || true' EXIT
cat >"$work/compose.yaml" <<EOF
services:
  db:
    image: $image
    command: ["sleep", "300"]
    healthcheck:
      test: ["CMD", "true"]
      interval: 2s
      timeout: 1s
      retries: 3
  app:
    image: $image
    command: ["sleep", "300"]
    depends_on:
      db:
        condition: service_healthy
EOF
chown -R "$user" "$work"
compose_started=1
if ! compose_out=$(run_user "cd $work && COMPOSE_PROGRESS=plain podman compose up -d" 2>&1); then
	printf '%s\n' "$compose_out" | tail -40 >&2
	fail 'podman compose up failed'
fi

cid=
i=0
while [ "$i" -lt 60 ]; do
	cid=$(run_user "podman ps --filter label=com.docker.compose.service=db --format '{{.ID}}' | head -n1")
	[ -n "$cid" ] && break
	i=$((i + 1))
	sleep 1
done
[ -n "$cid" ] || fail 'compose db container did not appear'

status=
i=0
while [ "$i" -lt 60 ]; do
	status=$(run_user "podman inspect $cid --format '{{.State.Health.Status}}'" 2>/dev/null || true)
	[ "$status" = healthy ] && break
	i=$((i + 1))
	sleep 1
done
[ "$status" = healthy ] || {
	run_user "podman inspect $cid --format '{{json .State.Health}}'" >&2 || true
	run_user "systemctl --user list-timers --all --no-legend" >&2 || true
	fail "healthcheck status: ${status:-unknown}"
}
pass 'healthcheck-gated compose dependency'

run_user "systemctl --user list-timers --all --no-legend" | grep -q "$cid" ||
	fail 'no transient healthcheck timer for the container'
pass 'transient healthcheck timer'

run_user "podman events --stream=false --since 5m --format '{{.Status}}'" |
	grep -q -E 'start|create' || fail 'no podman events visible'
pass 'podman events'

run_user "cd $work && DOCKER_HOST=unix:///run/user/$uid/podman/podman.sock docker-compose ps" >/dev/null ||
	fail 'docker-compose cannot use the rootless socket'
pass 'docker-compose over the Podman API'

run_user "cd $work && podman compose down" || fail 'podman compose down failed'
compose_started=
rm -rf "$work"

# --- Quadlet ----------------------------------------------------------------
mkdir -p "$home/.config/containers/systemd"
quadlet="$home/.config/containers/systemd/podman-smoke.container"
cat >"$quadlet" <<EOF
[Container]
Image=$image
Exec=sleep 60
EOF
chown -R "$user" "$home/.config/containers"
run_user 'systemctl --user daemon-reload'
run_user 'systemctl --user start podman-smoke.service' || {
	rm -f "$quadlet"
	fail 'quadlet service failed to start'
}
run_user 'systemctl --user is-active --quiet podman-smoke.service' ||
	fail 'quadlet service is not active'
run_user 'systemctl --user stop podman-smoke.service'
rm -f "$quadlet"
run_user 'systemctl --user daemon-reload'
pass 'quadlet generator'

printf 'PASS: podman systemd guest smoke checks\n'
