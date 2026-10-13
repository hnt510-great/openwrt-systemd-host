#!/bin/sh
# Run on the target as an ordinary user with the two controlled probe images.
set -eu
[ "$(id -u)" -ne 0 ] || { echo "Run as an ordinary user" >&2; exit 1; }
[ "$#" -eq 2 ] || { echo "Usage: $0 legacy-probe.AppImage modern-probe.AppImage" >&2; exit 1; }
work=$(mktemp -d "${TMPDIR:-/tmp}/appimage-smoke.XXXXXX")
trap 'rm -rf -- "$work"' EXIT HUP INT TERM
for image do
	image=$(readlink -f "$image")
	"$image" --cli 'argument with spaces' > "$work/mount.log"
	grep -q '^APPIMAGE_PROBE_FUSE=1$' "$work/mount.log"
	grep -q '^APPIMAGE_PROBE_ARGUMENT=argument with spaces$' "$work/mount.log"
	appdir=$(sed -n 's/^APPIMAGE_PROBE_APPDIR=//p' "$work/mount.log")
	# Allow the runtime's unmount helper to finish after the payload exits.
	i=0
	while grep -Fq " $appdir " /proc/self/mountinfo; do
		[ "$i" -lt 20 ] || { echo "AppImage mount leaked: $appdir" >&2; exit 1; }
		i=$((i + 1))
		sleep 1
	done
	TMPDIR="$work" "$image" --appimage-extract-and-run --cli 'argument with spaces' > "$work/extract.log"
	grep -q '^APPIMAGE_PROBE_FUSE=0$' "$work/extract.log"
	grep -q '^APPIMAGE_PROBE_ARGUMENT=argument with spaces$' "$work/extract.log"
	printf 'PASS mounted launch, arguments, cleanup and extraction: %s\n' "$image"
done
