#!/bin/sh
# Run as root inside a disposable native-systemd OpenWrt VM.
set -eu
[ "$(cat /proc/1/comm)" = systemd ]
[ "$(readlink /bin)" = usr/bin ]
[ "$(readlink /sbin)" = usr/sbin ]
[ "$(readlink /lib)" = usr/lib ]
[ -d /run ] && [ ! -L /run ]
[ "$(readlink /var/run)" = /run ]
systemctl is-active openwrt-ubusd openwrt-procd openwrt-services dbus systemd-journald
ubus call system board >/dev/null
ubus call network.interface.lan status | grep -q '"up": true'
test -S /dev/log
test -S /run/dbus/system_bus_socket
/usr/libexec/openwrt-dbus-ready --check
grep -q memory /sys/fs/cgroup/cgroup.controllers
grep -q pids /sys/fs/cgroup/cgroup.controllers
! grep -q '^[^#[:space:]]' /etc/apk/repositories.d/distfeeds.list
test "$(wc -c < /etc/machine-id)" -eq 33
/bin/busybox sha256sum /etc/machine-id | /bin/busybox sha256sum -sc -
test ! -e /usr/lib/systemd/system-generators/systemd-ssh-generator

cleanup() {
	systemctl stop openwrt-smoke.timer openwrt-smoke.socket 'openwrt-smoke@*.service' openwrt-smoke-tick.service || true
	rm -f /run/systemd/system/openwrt-smoke* /run/openwrt-smoke.sock /tmp/openwrt-smoke-tick
	systemctl daemon-reload
}
trap cleanup EXIT HUP INT TERM
cat > /run/systemd/system/openwrt-smoke-tick.service <<'EOF'
[Service]
Type=oneshot
ExecStart=/bin/sh -c 'echo tick >> /tmp/openwrt-smoke-tick'
EOF
cat > /run/systemd/system/openwrt-smoke.timer <<'EOF'
[Timer]
OnActiveSec=1
AccuracySec=100ms
Unit=openwrt-smoke-tick.service
EOF
cat > /run/systemd/system/openwrt-smoke.socket <<'EOF'
[Socket]
ListenStream=/run/openwrt-smoke.sock
Accept=yes
EOF
cat > /run/systemd/system/openwrt-smoke@.service <<'EOF'
[Service]
ExecStart=/bin/sh -c 'cat; sleep 15'
StandardInput=socket
StandardOutput=socket
MemoryMax=32M
TasksMax=8
EOF
systemctl daemon-reload
systemctl start openwrt-smoke.timer openwrt-smoke.socket
sleep 3
grep -q tick /tmp/openwrt-smoke-tick
printf 'socket-activation-check\n' | socat -t 1 - UNIX-CONNECT:/run/openwrt-smoke.sock | grep -q socket-activation-check
instance=$(systemctl list-units --type=service --plain --no-legend 'openwrt-smoke@*.service' | awk 'NR == 1 {print $1}')
test -n "$instance"
cgroup=$(systemctl show "$instance" -p ControlGroup --value)
test "$(cat /sys/fs/cgroup"$cgroup"/memory.max)" = 33554432
test "$(cat /sys/fs/cgroup"$cgroup"/pids.max)" = 8
systemctl stop "$instance"
! systemctl is-active -q "$instance"
echo native-journal-check | systemd-cat -t openwrt-systemd-smoke
journalctl --sync
journalctl -b -t openwrt-systemd-smoke --no-pager | grep -q native-journal-check
logger -t openwrt-systemd-smoke router-log-check
attempt=0
until journalctl -b -t openwrt-systemd-smoke --no-pager | grep -q router-log-check &&
	logread -e router-log-check | grep -q router-log-check; do
	attempt=$((attempt + 1))
	[ "$attempt" -lt 5 ] || exit 1
	sleep 1
done
sysupgrade -l | grep -q /etc/machine-id
echo 'native boot, router bridge, timer, socket, cgroup limits and both log paths passed'
