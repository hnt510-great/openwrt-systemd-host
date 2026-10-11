#!/bin/sh
# Read-only checks on a native guest; optionally check an already logged-in user.
set -eu
[ "$(id -u)" = 0 ]
[ "$(cat /proc/1/comm)" = systemd ]
systemctl is-active --quiet systemd-logind polkit dbus systemd-user-sessions
systemctl show systemd-logind -p ActiveState -p SubState
pkaction --action-id org.freedesktop.systemd1.manage-units
[ "$(stat -c '%a:%u' /usr/lib/polkit-1/polkit-agent-helper-1)" = '4755:0' ]
[ -f /usr/lib/security/pam_systemd.so ]
grep -q 'session.*pam_systemd.so' /etc/pam.d/sshd
grep -q 'session.*pam_systemd.so' /etc/pam.d/login
grep -q 'session.*pam_systemd.so' /etc/pam.d/openwrt-desktop
/usr/sbin/sshd -T | grep -qi '^UsePAM yes$'
case "$(readlink -f /var/lib/systemd/linger)" in
	/var/lib/systemd/linger) mountpoint -q /var/lib/systemd/linger ;;
	/tmp/lib/systemd/linger) mountpoint -q /tmp/lib/systemd/linger ;;
	*) exit 1 ;;
esac
if [ "$#" -gt 0 ]; then
	uid=$(id -u "$1")
	[ "$uid" -ge 1000 ]
	[ "$(stat -c '%a:%u' "/run/user/$uid")" = "700:$uid" ]
	[ -S "/run/user/$uid/bus" ]
	systemctl is-active --quiet "user@$uid.service" "user-runtime-dir@$uid.service"
	loginctl show-user "$1" -p RuntimePath -p Linger -p State -p Sessions
fi
loginctl list-sessions --no-pager
printf 'systemd authorization and session smoke checks passed\n'
