#!/bin/sh
# Run inside a disposable native-systemd OpenWrt VM with libvirt installed.
set -eu
[ "$(cat /proc/1/comm)" = systemd ]
systemctl is-active openwrt-services virtqemud virtlogd.socket virtlockd.socket
virsh -c qemu:///system version
virsh list --all
virsh capabilities | grep -q "domain type='qemu'"
test -c /dev/kvm
virsh capabilities | grep -q "domain type='kvm'"
id libvirt-qemu
grep '^libvirt-qemu:' /etc/passwd | grep -q '/bin/false$'
grep '^libvirt-qemu:' /etc/shadow | grep -q ':[!*x]:'
test "$(stat -c %a /run/libvirt/virtqemud-sock)" = 600
test "$(stat -c %U /run/libvirt/virtqemud-sock)" = root
test "$(stat -c %a /run/libvirt/virtqemud-sock-ro)" = 600
test "$(stat -c %a /run/libvirt/virtqemud-admin-sock)" = 600
test "$(stat -c %a /run/libvirt/virtlogd-sock)" = 600
test "$(stat -c %a /run/libvirt/virtlockd-sock)" = 600
grep -q " $(readlink -f /var/lib/libvirt) " /proc/mounts
marker="libvirt-state-smoke-$$"
printf '%s\n' "$marker" > /srv/libvirt/state/.smoke
grep -qx "$marker" /var/lib/libvirt/.smoke
rm /srv/libvirt/state/.smoke
ubus call network.interface.lan status | grep -q '"up": true'
! ip link show virbr0 >/dev/null 2>&1
test ! -e /usr/sbin/virtnetworkd
test ! -e /usr/sbin/virtnwfilterd
test ! -e /usr/sbin/virtproxyd
sysupgrade -l | grep -q '^/etc/libvirt/'
echo libvirt-native-smoke-passed
