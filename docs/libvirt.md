# Libvirt and virsh on native-systemd OpenWrt

This package targets x86_64/glibc with CONFIG_OPENWRT_SYSTEMD=y. It provides
libvirt 12.8.0, virsh, modular QEMU/secret/directory-storage daemons, virtlogd
and virtlockd. Select CONFIG_PACKAGE_libvirt-daemon=y and
CONFIG_PACKAGE_virsh=y, run make defconfig, then build:

    make package/custom/libvirt/compile -j4 V=s
    make -j2 V=s

Firmware and matching signed APKs are under bin/systemd. Use APKs from this
build, rather than Debian or Alpine binaries. The library and client are
separate APKs; the daemon package pulls in the client and QEMU runtime.

## Services and permissions

On a native boot, the packaged systemd sockets and virtqemud start after
openwrt-services.service and the persistent state mount. There is no procd
startup script, so the recovery and failsafe entries do not launch guests.

    virsh -c qemu:///system version
    virsh list --all
    virsh capabilities
    systemctl status virtqemud virtstoraged virtlogd virtlockd
    journalctl -b -u virtqemud --no-pager

The default URI is qemu:///system. All packaged libvirt UNIX sockets are
root-owned and mode 0600. Run the client as root or through sudo. TCP/TLS
listeners and the remote proxy are not included. Ordinary-user session
management is outside the supported scope. QEMU processes run under the locked, non-login libvirt-qemu service
account, with supplementary membership in the existing kvm group. No human
account, password or SSH key is seeded.

AppArmor/SELinux and private mount namespaces are disabled in this first
integration; libvirt retains DAC ownership management, disk locking and
cgroup isolation. OpenWrt owns device hotplug, bridges, DHCP and firewall
rules. This build does not expose libvirt network, interface, nwfilter or
device-passthrough management. The host uses the existing OpenWrt shutdown
sequence; a native helper first requests ACPI shutdown for guests and waits
up to 60 seconds. Shut guests down explicitly before maintenance if they
cannot handle ACPI shutdown.

The secret service uses a 32-byte key generated on first boot under
/srv/libvirt/state/secrets, mode 0600, and passes it through systemd's
credential loader. Its parent directory is mode 0700. This avoids depending
on the volatile host credential key under /var/lib/systemd. Preserve the
entire state directory, including this key, when backing up secret values.

## Persistent state and storage

OpenWrt's /var is normally backed by /tmp. The package bind-mounts
/srv/libvirt/state at /var/lib/libvirt before starting any daemon. Persistent
domain and pool definitions are in /etc/libvirt; runtime sockets remain in
/run/libvirt, while logs and capability caches under /var are temporary.
Do not unmount state storage while guests or libvirt daemons are running.

The example image directory is /srv/libvirt/images. With the default overlay,
space is limited by the root filesystem. For large guests, configure an
external filesystem using OpenWrt fstab, then define a directory pool there.
The directory must be mounted before starting its pool or autostart guests;
for boot-time external storage add RequiresMountsFor=/your/mount/path to a
virtqemud.service drop-in. Do not allow an absent disk to silently fall back
to writing guest disks into the root overlay.

    virsh pool-define-as local dir --target /srv/libvirt/images
    virsh pool-start local
    virsh pool-autostart local
    virsh vol-create-as local openwrt-vm.qcow2 4G --format qcow2
    virsh vol-list local

This creates an empty disk. Install a guest OS or convert a supplied bootable
image to that path with qemu-img before expecting it to boot. Use a raw or
qcow2 image suitable for SeaBIOS; OVMF/UEFI guest firmware is outside v1.

## Define and run a guest

Copy /usr/share/libvirt/examples/openwrt-vm.xml to a writable location and
adjust the name, memory, disk path and bridge for your installation:

    virsh define /usr/share/libvirt/examples/openwrt-vm.xml
    virsh start openwrt-vm
    virsh console openwrt-vm
    virsh shutdown openwrt-vm
    virsh autostart openwrt-vm

Exit the serial console with Ctrl+]. The guest OS must enable a serial
console. The example uses a virtio NIC bridged to br-lan; OpenWrt dnsmasq
provides DHCP using the existing LAN policy. There is no libvirt-created
virbr0 or second DHCP server.

The example uses KVM and host-passthrough CPU. Check /dev/kvm and virsh
capabilities first. A machine's CPU and firmware must expose VT-x/AMD-V; a
VM host must expose nested virtualization. For deliberate software emulation,
change the domain type to qemu and remove the host-passthrough cpu element.
Do not present a successful software-emulated boot as proof of KVM support.

Existing manually started QEMU processes remain unmanaged. Import their
configuration as domain XML separately; stop them before opening the same
disk under libvirt.

## Backup and upgrades

The package marks /etc/libvirt as configuration so it is included in the
normal OpenWrt configuration backup. Verify the selection with sysupgrade -l.
Guest images and /srv/libvirt/state are not included in the firmware backup:
back them up separately with guests stopped, and preserve external disks.
Before reflashing, boot the existing procd recovery entry as described in
systemd.md. A firmware upgrade alone is not a virtual-machine data backup.

Validation results and exact firmware hash are recorded in
[libvirt-validation.md](libvirt-validation.md).
