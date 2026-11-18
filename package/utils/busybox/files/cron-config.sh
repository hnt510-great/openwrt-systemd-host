#!/bin/sh
# Shared cron configuration helper.

cron_has_entries() {
	[ -n "$(ls /etc/crontabs/ 2>/dev/null)" ]
}

cron_resolve_loglevel() {
	CRON_LOGLEVEL="$(uci_get "system.@system[0].cronloglevel")"
	if [ -n "$CRON_LOGLEVEL" ]; then
		/sbin/validate_data uinteger "$CRON_LOGLEVEL" 2>/dev/null || {
			echo "validation failed" >&2
			return 1
		}
	else
		CRON_LOGLEVEL=7
	fi
}

cron_prepare_spool() {
	mkdir -p /var/spool/cron
	ln -s /etc/crontabs /var/spool/cron/ 2>/dev/null || :
}
