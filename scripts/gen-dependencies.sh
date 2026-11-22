#!/usr/bin/env bash
#
# Copyright (C) 2012 OpenWrt.org
#
# This is free software, licensed under the GNU General Public License v2.
# See /LICENSE for more information.
#
set -e -o pipefail
SELF=${0##*/}

READELF="${READELF:-readelf}"
OBJCOPY="${OBJCOPY:-objcopy}"
XARGS="${XARGS:-xargs -r}"

[ "$#" -eq 0 ] && {
  echo "$SELF: no directories / files specified" >&2
  echo "usage: $SELF [PATH...]" >&2
  exit 1
}

find "$@" -type f -exec file -N {} + | \
  sed -n -e 's/^\(.*\):.*ELF.*\(executable\|shared object\).*,.*/\1/p' | \
  $XARGS -n1 $READELF -d | \
  awk '$2 ~ /NEEDED/ && $NF !~ /interpreter/ && $NF ~ /^\[?lib.*\.so/ { gsub(/[\[\]]/, "", $NF); print $NF }' | \
  sort -u

tmp=$(mktemp -d "${TMP_DIR:-/tmp}/dep.XXXXXXXX")
trap 'rm -rf "$tmp"' EXIT
find "$@" -type f -name '*.ko' -print0 > "$tmp/modules"
while IFS= read -r -d '' kmod; do
	"$OBJCOPY" -O binary -j .modinfo "$kmod" "$tmp/modinfo"
	tr '\000' '\n' < "$tmp/modinfo" | sed -ne '/^depends=.\+/ { s/^depends=//; s/,/.ko\n/g; s/$/.ko/p; }'
done < "$tmp/modules" | sort -u
