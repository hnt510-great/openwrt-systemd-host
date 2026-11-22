#!/usr/bin/env bash
#
# Copyright (C) 2006 OpenWrt.org
#
# This is free software, licensed under the GNU General Public License v2.
# See /LICENSE for more information.
#
set -e -o pipefail
SELF=${0##*/}

[ -z "$STRIP" ] && {
  echo "$SELF: strip command not defined (STRIP variable not set)" >&2
  exit 1
}

[ "$#" -eq 0 ] && {
  echo "$SELF: no directories / files specified" >&2
  echo "usage: $SELF [PATH...]" >&2
  exit 1
}

find "$@" -not -path '*/lib/firmware/*' -type f -exec file -N {} + | \
  sed -n -e 's/^\(.*\):.*ELF.*\(executable\|relocatable\|shared object\).*,.*/\1:\2/p' | \
(
  IFS=":"
  while read -r F S; do
    echo "$SELF: $F: $S"
	if [ "${S}" = "relocatable" ]; then
		[ "${F##*.}" = "o" ] && continue
		eval "$STRIP_KMOD \"\$F\""
	else
		b=$(stat -c '%a' "$F")
		if [ -n "$PATCHELF" ] && [ -n "$TOPDIR" ]; then
			old_rpath=""; new_rpath=""
			# Static executables have no dynamic section for patchelf to inspect.
			if ! old_rpath=$("$PATCHELF" --print-rpath "$F" 2>/dev/null); then
				case "$(file -b "$F")" in
					*statically\ linked*|*static-pie\ linked*) ;;
					*)
						echo "$SELF: $F: patchelf --print-rpath failed" >&2
						exit 1
						;;
				esac
			fi
			for path in $old_rpath; do
				case "$path" in
					/lib/[^/]*|/usr/lib/[^/]*|\$ORIGIN/*|\$ORIGIN) new_rpath="${new_rpath:+$new_rpath:}$path" ;;
					*) echo "$SELF: $F: removing rpath $path" ;;
				esac
			done
			[ "$new_rpath" = "$old_rpath" ] || "$PATCHELF" --set-rpath "$new_rpath" "$F"
		fi
		eval "$STRIP \"\$F\""
		a=$(stat -c '%a' "$F")
		[ "$a" = "$b" ] || chmod "$b" "$F"
	fi
  done
)
