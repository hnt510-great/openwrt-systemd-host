# Shared POSIX helpers; sourced by the root-only setup and service scripts.
DESKTOP_SESSIONS_DIR=/usr/libexec/openwrt-desktop/sessions.d
DESKTOP_SESSION_REQUIRE_ROOT=1

desktop_validate_session_id() {
	case "$1" in
		''|*[!a-z0-9_-]*|-*|_*|?????????????????????????????????*)
			desktop_error "Invalid desktop session '$1'"
			return 1
			;;
	esac
}

desktop_session_plugin_path() {
	local id path owner
	id="$1"
	desktop_validate_session_id "$id" || return 1
	path="$DESKTOP_SESSIONS_DIR/$id"
	[ -f "$path" ] && [ ! -L "$path" ] || {
		desktop_error "Desktop session '$id' is not registered"
		return 1
	}
	if [ "$DESKTOP_SESSION_REQUIRE_ROOT" = 1 ]; then
		owner="$(stat -c %u "$path" 2>/dev/null || :)"
		[ "$owner" = 0 ] || {
			desktop_error "Unsafe desktop session plugin '$id'"
			return 1
		}
	fi
	printf '%s\n' "$path"
}

desktop_load_session() {
	local id path
	id="$1"
	path="$(desktop_session_plugin_path "$id")" || return 1
	SESSION_ID=
	SESSION_TITLE=
	SESSION_DESCRIPTION=
	SESSION_EXEC=
	SESSION_SUPPORTS_RDP=0
	SESSION_SUPPORTS_KMS_SCHEDULING=0
	SESSION_CREDENTIAL_BACKEND=
	SESSION_RDP_UNIT=
	SESSION_UNSET_VARS=
	desktop_session_check() { [ -n "$SESSION_EXEC" ] && [ -x "$SESSION_EXEC" ]; }
	desktop_session_setup() { return 0; }
	desktop_session_user_setup() { return 0; }
	desktop_session_credential_prop() { return 0; }
	desktop_session_unlock() { return 0; }
	desktop_session_exec() { desktop_error "Desktop session plugin '$id' has no exec hook"; return 1; }
	desktop_session_stop() { return 0; }
	# shellcheck disable=SC1090
	. "$path"
	[ "$SESSION_ID" = "$id" ] || {
		desktop_error "Desktop session plugin '$id' has mismatched SESSION_ID"
		return 1
	}
}

desktop_list_available_sessions() {
	local path name owner
	[ -d "$DESKTOP_SESSIONS_DIR" ] || return 0
	for path in "$DESKTOP_SESSIONS_DIR"/*; do
		[ -f "$path" ] && [ ! -L "$path" ] || continue
		name="${path##*/}"
		case "$name" in
			''|*[!a-z0-9_-]*|-*|_*|?????????????????????????????????*) continue ;;
		esac
		if [ "$DESKTOP_SESSION_REQUIRE_ROOT" = 1 ]; then
			owner="$(stat -c %u "$path" 2>/dev/null || :)"
			[ "$owner" = 0 ] || continue
		fi
		if ( desktop_load_session "$name" >/dev/null 2>&1 && desktop_session_check >/dev/null 2>&1 ); then
			printf '%s\n' "$name"
		fi
	done
}

desktop_resolve_session() {
	local configured avail count first list id
	configured="${1:-}"
	if [ -n "$configured" ]; then
		if ( desktop_load_session "$configured" && desktop_session_check ); then
			printf '%s\n' "$configured"
			return 0
		fi
		desktop_error "Desktop session '$configured' is not installed or unavailable"
		return 1
	fi
	count=0
	first=
	list=
	avail="$(desktop_list_available_sessions)"
	for id in $avail; do
		count=$((count + 1))
		if [ "$count" -eq 1 ]; then
			first="$id"
			list="$id"
		else
			list="$list, $id"
		fi
	done
	if [ "$count" -eq 1 ]; then
		printf '%s\n' "$first"
		return 0
	fi
	if [ "$count" -eq 0 ]; then
		desktop_error 'No desktop session is installed or available'
		return 1
	fi
	desktop_error "Multiple desktop sessions are available ($list); configure desktop.main.session explicitly"
	return 1
}

desktop_collect_unset_vars() {
	local vars path name owner line extra var
	vars="WAYLAND_SOCKET GTK_IM_MODULE GTK_IM_MODULE_FILE LIBSEAT_BACKEND XDG_CURRENT_DESKTOP XDG_SESSION_DESKTOP DESKTOP_SESSION XDG_SESSION_TYPE QT_IM_MODULE XMODIFIERS MUTTER_DEBUG_KMS_SCHEDULING_PRIORITY"
	if [ -d "$DESKTOP_SESSIONS_DIR" ]; then
		for path in "$DESKTOP_SESSIONS_DIR"/*; do
			[ -f "$path" ] && [ ! -L "$path" ] || continue
			name="${path##*/}"
			case "$name" in
				''|*[!a-z0-9_-]*|-*|_*|?????????????????????????????????*) continue ;;
			esac
			if [ "$DESKTOP_SESSION_REQUIRE_ROOT" = 1 ]; then
				owner="$(stat -c %u "$path" 2>/dev/null || :)"
				[ "$owner" = 0 ] || continue
			fi
			line="$(sed -n 's/^SESSION_UNSET_VARS=//p' "$path" | head -n 1)"
			extra="$(printf '%s' "$line" | tr -d "\"'")"
			for var in $extra; do
				case "$var" in
					''|[0-9]*|*[!A-Za-z0-9_]*) continue ;;
				esac
				case " $vars " in
					*" $var "*) ;;
					*) vars="$vars $var" ;;
				esac
			done
		done
	fi
	printf '%s\n' "$vars"
}

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
