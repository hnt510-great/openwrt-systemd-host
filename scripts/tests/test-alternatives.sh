#!/bin/sh
set -eu
test_root=$(mktemp -d)
trap 'rm -rf "$test_root"' EXIT HUP INT TERM
mkdir -p "$test_root/usr/bin" "$test_root/usr/lib/apk/packages"
ln -s usr/lib "$test_root/lib"
touch "$test_root/usr/bin/busybox" "$test_root/usr/bin/openwrt-test-mount"
echo '100:/usr/bin/mount:/usr/bin/busybox' > "$test_root/lib/apk/packages/busybox.alternatives"
echo '200:/usr/bin/mount:/usr/bin/openwrt-test-mount' > "$test_root/lib/apk/packages/test.alternatives"
IPKG_INSTROOT="$test_root"
export IPKG_INSTROOT
. "$(dirname "$0")/../../package/base-files/files/lib/functions.sh"
update_alternatives install test
update_alternatives install busybox
[ "$(readlink "$test_root/usr/bin/mount")" = /usr/bin/openwrt-test-mount ]
update_alternatives remove test
[ "$(readlink "$test_root/usr/bin/mount")" = /usr/bin/busybox ]
update_alternatives install test
[ "$(readlink "$test_root/usr/bin/mount")" = /usr/bin/openwrt-test-mount ]
rm "$test_root/usr/bin/openwrt-test-mount"
update_alternatives install busybox
[ "$(readlink "$test_root/usr/bin/mount")" = /usr/bin/busybox ]
echo 'alternative install, removal, reinstall and missing payload checks passed'
