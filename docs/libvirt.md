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
account, with supplementary membership in the kvm and render groups. No human
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

## Graphics examples

Host CPU passthrough, VirtIO disk and VirtIO network are already included in
`/usr/share/libvirt/examples/openwrt-vm.xml`. KVM is required for host CPU
passthrough; guests need the appropriate VirtIO drivers. The new graphics
examples preserve this CPU/storage/bridge setup:

- `openwrt-graphics-vm.xml`: SPICE, VirtIO video, 3D disabled; works without a host GPU.
- `openwrt-graphics-gl-vm.xml`: SPICE, VirtIO video, 3D enabled; choose an existing usable render node.

Create the referenced qcow2 disk or change its source path, then define the
chosen example. These commands create a new guest, not modify an existing one:

```sh
qemu-img create -f qcow2 /srv/libvirt/images/openwrt-graphics-vm.qcow2 8G
virsh -c qemu:///system define /usr/share/libvirt/examples/openwrt-graphics-vm.xml
virsh -c qemu:///system start openwrt-graphics-vm
virsh -c qemu:///system domcapabilities --virttype kvm
virsh -c qemu:///system dumpxml openwrt-graphics-vm
```

A `virt-install` example for importing an already bootable Linux disk:

```sh
virt-install --connect qemu:///system --name linux-spice \
  --memory 1024 --vcpus 2 --cpu host-passthrough --osinfo generic \
  --import --disk path=/srv/libvirt/images/linux.qcow2,format=qcow2,bus=virtio \
  --network bridge=br-lan,model=virtio \
  --graphics spice,listen=none --video virtio --sound ich9 --noautoconsole
```

For explicit OpenGL use `--graphics spice,listen=none,gl.enable=yes,gl.rendernode=/dev/dri/renderD128`
and `--video virtio,model.acceleration.accel3d=yes`. The equivalent XML is:

```xml
<graphics type='spice'>
  <listen type='none'/>
  <gl enable='yes' rendernode='/dev/dri/renderD128'/>
</graphics>
<video>
  <model type='virtio' heads='1' primary='yes'>
    <acceleration accel3d='yes'/>
  </model>
</video>
```

Changing an existing VM's video, CPU or disk bus requires stopping it first
and ensuring its operating system has the drivers. Nothing rewrites existing
VM definitions automatically. A successful GL boot must be followed by a
renderer check in the guest, for example `glxinfo -B` in an X11 session or
`eglinfo`/`wflinfo` for EGL/Wayland. A renderer containing softpipe/llvmpipe is
software rendering. Nested VirtIO/VirGL results do not certify physical Intel
GPU performance. No PCI passthrough or Vulkan support is added here.

## Virtual machine audio

Both graphics examples include an ICH9 HDA sound card and an explicit SPICE
audio backend. Guest sound drivers must be installed. With a connected
virt-manager/SPICE viewer, playback and recording travel through that viewer.
On this desktop its GStreamer Pulse plugin connects to `pipewire-pulse`.
SPICE GTK declares its audio conversion, resampling, app, autodetection and
Pulse plugin dependencies directly. The local virt-manager/virt-install
defaults also create a sound card for new SPICE guests; existing definitions
are unchanged.
The viewer's user needs [desktop audio](desktop-audio.md) enabled. A remote
SPICE viewer uses the remote client's audio devices. Closing the viewer stops
this audio route; no native QEMU PipeWire backend is needed for SPICE audio.

### Direct host PipeWire audio (optional)

Merge `configs/libvirt-pipewire.config` into a copy of the existing build
configuration, normalize it with `make defconfig`, and rebuild QEMU and
libvirt. `QEMU_AUDIO_PIPEWIRE` defaults to disabled and adds `libpipewire` to
QEMU when enabled. It does not change the SPICE default or existing VM XML.
The packages feed change is exported in `configs/libvirt-audio-feeds.json`.

After installing the rebuilt packages, enroll the chosen desktop account with
`desktop-audio-setup USER`. As root, enable access for its numeric UID:

```sh
audio_uid=$(id -u USER)
systemctl enable --now "libvirt-pipewire-access@$audio_uid.path"
systemctl start "libvirt-pipewire-access@$audio_uid.service"
```

The opt-in path unit reapplies an execute ACL on that user's runtime directory
and a read/write ACL on its `pipewire-0` socket after directory/socket creation
or recreation. File operations run as the audio user, not root. Other runtime
sockets do not receive ACLs. This grants **all VMs running as libvirt-qemu**
access to that user's PipeWire server, including playback and capture. Use
SPICE when separate viewer identities or client-side audio are required.
The unit is not enabled automatically, and it does not start an audio server.

Stop the selected VM before changing its devices. Keep its existing graphics
and video configuration and add or replace these elements under `<devices>`:

```xml
<sound model='ich9'><audio id='1'/></sound>
<audio id='1' type='pipewire' runtimeDir='/run/user/1000'/>
```

Replace `1000` with `audio_uid`. A complete new-VM example is installed as
`/usr/share/libvirt/examples/openwrt-graphics-pipewire-vm.xml`; adjust its UID,
disk path, name and network before defining it. Direct audio remains available
when the viewer closes, while the desktop user's PipeWire server is running.
It does not enable audio in a guest without a sound driver, or during recovery.
For `qemu:///session` under the same desktop user, no cross-user ACL is needed;
session networking and disk access must be configured separately.

Verify the installed QEMU lists `pipewire` in `qemu-system-x86_64 -audiodev help`,
check `systemctl status libvirt-pipewire-access@UID.path` and the matching
service journal, then test guest playback and recording. `getfacl` on the
runtime directory and socket should show only the explicit libvirt-qemu grant.
Test again after restarting the user's PipeWire service and after reboot.
Audio content testing is required; a listed backend alone proves no playback.

To revoke access, first stop VMs using this backend, then run as root:

```sh
systemctl disable --now "libvirt-pipewire-access@$audio_uid.path"
systemctl stop "libvirt-pipewire-access@$audio_uid.service"
/usr/libexec/libvirt-pipewire-access "$audio_uid" revoke
```

Switch affected VMs back to `<audio id='1' type='spice'/>` before starting them.

Build and disposable-VM results are recorded in
[libvirt-audio-validation.md](libvirt-audio-validation.md).
