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
	case "$1" in ''|*[!0-9]*) desktop_error 'Invalid RDP port'; return 1 ;; esac
	[ "$1" -ge 1024 ] && [ "$1" -le 65535 ] || {
		desktop_error 'RDP port must be between 1024 and 65535'; return 1;
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

# Root-only account setup owns the directory; key files belong to the user.
desktop_setup_tls() {
	local key cert tmp address
	[ ! -L /etc/desktop ] && [ ! -L /etc/desktop/tls ] || {
		desktop_error 'Unsafe desktop TLS directory'; return 1;
	}
	mkdir -p /etc/desktop/tls
	chmod 0755 /etc/desktop /etc/desktop/tls
	key="/etc/desktop/tls/$DESKTOP_USER_NAME.key"
	cert="/etc/desktop/tls/$DESKTOP_USER_NAME.crt"
	if [ ! -e "$key" ] && [ ! -e "$cert" ]; then
		address="$(desktop_lan_address)"
		case "$address" in ''|0.0.0.0|*[!0-9.]*) desktop_error 'Bring up the LAN before desktop-setup'; return 1 ;; esac
		tmp="$(mktemp -d /etc/desktop/.tls.XXXXXX)" || return 1
		if ! openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 3650 \
		-subj '/CN=OpenWrt GNOME desktop' -addext "subjectAltName=IP:$address" \
		-keyout "$tmp/key" -out "$tmp/cert" >/dev/null 2>&1; then
			rm -rf "$tmp"; return 1
		fi
		chmod 0600 "$tmp/key"
		chmod 0644 "$tmp/cert"
		chown "$DESKTOP_USER_UID:$DESKTOP_USER_GID" "$tmp/key" "$tmp/cert"
		mv "$tmp/key" "$key"
		mv "$tmp/cert" "$cert"
		rmdir "$tmp"
	fi
	[ -f "$key" ] && [ ! -L "$key" ] && [ -f "$cert" ] && [ ! -L "$cert" ] || {
		desktop_error 'Desktop TLS credentials are incomplete or unsafe'; return 1;
	}
	openssl x509 -in "$cert" -noout -checkend 0 >/dev/null || return 1
	[ "$(openssl pkey -in "$key" -pubout 2>/dev/null)" = 	  "$(openssl x509 -in "$cert" -pubkey -noout 2>/dev/null)" ] || {
		desktop_error 'The TLS certificate and key do not match'; return 1;
	}
	chown "$DESKTOP_USER_UID:$DESKTOP_USER_GID" "$key" "$cert"
	chmod 0600 "$key"
	chmod 0644 "$cert"
}
