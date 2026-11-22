#!/usr/bin/env bash
set -e -o pipefail
[ -n "$1" -a -n "$2" ] || {
	echo "Usage: $0 <file> <directory>" >&2
	exit 1
}
[ -f "$1" -a -d "$2" ] || {
	echo "File/directory not found" >&2
	exit 1
}

(
	cd "$2"
	while IFS= read -r entry; do
		[ -n "$entry" ] || continue
		case "$entry" in
			.|./) continue ;;
		esac
		if [ -L "$entry" ] || [ ! -d "$entry" ]; then
			if [ -e "$entry" ] || [ -L "$entry" ]; then
				rm -- "$entry"
			fi
		fi
	done
) < "$1"

LC_ALL=C sort -r "$1" | (
	cd "$2"
	while IFS= read -r entry; do
		[ -n "$entry" ] || continue
		case "$entry" in
			.|./) continue ;;
		esac
		if [ -d "$entry" ] && [ ! -L "$entry" ]; then
			if ! rmdir -- "$entry" 2>/dev/null; then
				# Ignore normal non-empty shared directories; propagate real errors.
				if [ -z "$(ls -A -- "$entry" 2>/dev/null)" ]; then
					rmdir -- "$entry"
				fi
			fi
		fi
	done
)
