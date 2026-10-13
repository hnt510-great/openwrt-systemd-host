#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || { echo "Run this script as root" >&2; exit 1; }
case "${1:---simulate}" in
	--simulate) simulate=1 ;;
	--install) simulate=0 ;;
	*) echo "Usage: $0 [--simulate|--install]" >&2; exit 1 ;;
esac
cd -- "$(dirname -- "$0")"
sha256sum -c SHA256SUMS
set -- ./*.apk
apk --keys-dir /etc/apk/keys verify "$@"
if [ "$simulate" = 1 ]; then
	exec apk add --simulate --no-network --no-logfile "$@"
fi
exec apk add --no-network --no-logfile "$@"
