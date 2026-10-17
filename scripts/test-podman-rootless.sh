#!/bin/sh
# Run in a fresh ordinary-user native-systemd login session.
set -eu
[ "$(id -u)" -ne 0 ]
[ -n "${XDG_RUNTIME_DIR:-}" ]
test -r /dev/net/tun && test -w /dev/net/tun
test "$(podman info --format '{{.Host.Security.Rootless}}')" = true
test "$(podman info --format '{{.Host.CgroupManager}}')" = systemd
if [ -d /run/systemd/system ]; then
	test "$(podman info --format '{{.Host.EventLogger}}')" = journald
	test "$(podman info --format '{{.Host.LogDriver}}')" = journald
fi
podman unshare cat /proc/self/uid_map /proc/self/gid_map
podman unshare awk '$1 == 1 && $3 >= 65536 { ok=1 } END { exit !ok }' /proc/self/uid_map
podman unshare awk '$1 == 1 && $3 >= 65536 { ok=1 } END { exit !ok }' /proc/self/gid_map
image=${1:-docker.io/library/alpine:3.23}
podman run --rm "$image" sh -ec '
  id
  touch /tmp/podman-id-test
  chown 1234:2345 /tmp/podman-id-test
  test "$(stat -c %u:%g /tmp/podman-id-test)" = 1234:2345
  nslookup example.com
  wget -qO /dev/null https://example.com
'
podman ps
printf '%s\n' 'PASS: default rootless startup, subordinate IDs, DNS and HTTPS'
