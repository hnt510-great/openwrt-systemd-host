#!/bin/sh
# Run as root ONLY in a disposable native-systemd guest. clear deletes history.
# Run record, reboot the guest, then run check and optionally clear.
set -eu
[ "$(id -u)" = 0 ]
[ "$(cat /proc/1/comm)" = systemd ]
for unit in systemd-journald systemd-journal-flush.service openwrt-journal-rotate.timer; do
	systemctl is-active --quiet "$unit"
done
mountpoint -q "$(readlink -f /var/log/journal)"
[ "$(stat -c '%d:%i' /srv/journal)" = "$(stat -c '%d:%i' /var/log/journal)" ]
state=/srv/journal-smoke-boot
tag=openwrt-journal-persistence-smoke

case "${1:-}" in
	record)
		cat /proc/sys/kernel/random/boot_id > "$state"
		printf 'persistent-journal-smoke-%s\n' "$(cat "$state")" | systemd-cat -t "$tag"
		journalctl --sync
		journalctl --directory=/srv/journal -t "$tag" --no-pager | grep -q "persistent-journal-smoke-$(cat "$state")"
		echo 'recorded marker on persistent storage; reboot before check'
		;;
	check)
		boot=$(cat "$state")
		[ "$boot" != "$(cat /proc/sys/kernel/random/boot_id)" ]
		journalctl --boot="$(printf '%s' "$boot" | tr -d '-')" -t "$tag" --no-pager | grep -q "persistent-journal-smoke-$boot"
		journalctl --verify
		systemctl start openwrt-journal-rotate.service
		echo 'prior-boot marker retained and rotation service passed'
		;;
	clear)
		[ -f "$state" ]
		journalctl --sync
		journalctl --rotate --vacuum-size=1
		[ -z "$(journalctl -t "$tag" -o cat --no-pager)" ]
		echo post-clear-journal-smoke | systemd-cat -t "$tag"
		journalctl --sync
		journalctl -t "$tag" -o cat --no-pager | grep -qx post-clear-journal-smoke
		rm -f "$state"
		echo 'old history deleted; new logging continues'
		;;
	*)
		echo 'usage: sh journald-guest-smoke.sh record|check|clear (disposable VM only)' >&2
		exit 2
		;;
esac
