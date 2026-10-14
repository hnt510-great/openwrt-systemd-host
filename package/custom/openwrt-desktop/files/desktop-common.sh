# Shared POSIX helpers; sourced by the root-only setup and service scripts.
desktop_validate_mode() {
	[ "$1" = preferred ] && return 0
	case "$1" in ''|*[!0-9x@]*) desktop_error 'Invalid desktop display mode'; return 1 ;; esac
	printf '%s\n' "$1" | awk -F '[x@]' '
		/^[1-9][0-9]*x[1-9][0-9]*(@[1-9][0-9]*)?$/ {
			valid = $1 >= 320 && $1 <= 16384 && $2 >= 200 && $2 <= 16384 &&
				(NF == 2 || ($3 >= 1 && $3 <= 240))
		}
		END { exit !valid }
	' || { desktop_error 'Invalid desktop display mode'; return 1; }
}

desktop_validate_rdp() {
	case "$1:$2" in *[!0-9:]*|:*|*:) desktop_error 'Invalid RDP port or refresh rate'; return 1 ;; esac
	[ "$1" -ge 1024 ] && [ "$1" -le 65535 ] && [ "$1" -ne "$3" ] || {
		desktop_error 'RDP port must be between 1024 and 65535 and differ from VNC'; return 1;
	}
	[ "$2" -ge 1 ] && [ "$2" -le 60 ] || {
		desktop_error 'RDP refresh rate must be between 1 and 60'; return 1;
	}
}

desktop_error() {
	logger -t openwrt-desktop "$*"
	printf '%s\n' "$*" >&2
	return 1
}

desktop_validate_user() {
	local name record hash
	name="$1"
	case "$name" in
		''|-*|*[!a-zA-Z0-9_-]*) desktop_error 'Invalid desktop username'; return 1 ;;
	esac
	record="$(awk -F: -v name="$name" '$1 == name { print; exit }' /etc/passwd)"
	[ -n "$record" ] || { desktop_error "Account $name does not exist"; return 1; }
	IFS=: read -r DESKTOP_USER_NAME DESKTOP_USER_PASS DESKTOP_USER_UID \
		DESKTOP_USER_GID DESKTOP_USER_GECOS DESKTOP_USER_HOME DESKTOP_USER_SHELL <<EOF
$record
EOF
	case "$DESKTOP_USER_UID" in
		''|*[!0-9]*) desktop_error 'Invalid desktop UID'; return 1 ;;
	esac
	[ "$DESKTOP_USER_UID" -ge 1000 ] || {
		desktop_error 'The desktop requires an ordinary user with UID >= 1000'; return 1;
	}
	case "$DESKTOP_USER_GID" in
		''|*[!0-9]*) desktop_error 'Invalid desktop primary group'; return 1 ;;
	esac
	[ "$DESKTOP_USER_GID" -gt 0 ] || {
		desktop_error 'The desktop account must have a non-root primary group'; return 1;
	}
	case "$DESKTOP_USER_HOME" in
		/*) ;;
		*) desktop_error 'The account requires an absolute home directory'; return 1 ;;
	esac
	[ -d "$DESKTOP_USER_HOME" ] && [ -x "$DESKTOP_USER_SHELL" ] || {
		desktop_error 'Create the home directory and configure a valid login shell first'; return 1;
	}
	case "$DESKTOP_USER_SHELL" in
		*/false|*/nologin) desktop_error 'The account requires a login shell'; return 1 ;;
	esac
	hash="$(awk -F: -v name="$name" '$1 == name { print $2; exit }' /etc/shadow)"
	case "$hash" in
		''|'!'*|'*'*) desktop_error 'Set an unlocked, nonempty account password first'; return 1 ;;
	esac
}

desktop_lan_address() {
	ubus -S call network.interface.lan status 2>/dev/null |
		jsonfilter -e '@["ipv4-address"][0].address'
}

desktop_select_output() {
	local requested path name
	requested="${1:-auto}"
	case "$requested" in
		''|*[!a-zA-Z0-9_-]*) desktop_error 'Invalid DRM output name'; return 1 ;;
	esac
	for path in /sys/class/drm/card*-*/status; do
		[ -r "$path" ] || continue
		[ "$(cat "$path")" = connected ] || continue
		name="${path%/status}"
		name="${name##*/}"
		name="${name#*-}"
		[ "$requested" = auto ] || [ "$requested" = "$name" ] || continue
		printf '%s\n' "$name"
		return 0
	done
	desktop_error "No connected DRM output matches $requested"
}
