# Virtual Machine Manager on GNOME

The x86_64/glibc native-systemd desktop includes virt-manager as an
ordinary-user application. It connects to local modular libvirt daemons using
`qemu:///system`. GNOME provides the graphical session; OpenWrt owns host
bridges, DHCP and firewall policy.

## Setup and authorization

Create an ordinary user and configure [GNOME](gnome-desktop.md). As root,
explicitly authorize that existing account:

```sh
virt-manager-setup USER
```

The `libvirt-admin` group grants trusted-administrator access to local QEMU,
storage and secret resources. It is a role with privileges comparable to root.
Run the manager from the GNOME application overview or the desktop terminal:

```sh
/usr/libexec/virt-manager-launch
virsh -c qemu:///system list --all
```

Client UNIX sockets of virtqemud, virtstoraged, virtsecretd, virtnodedevd and
virtnwfilterd receive the configured group access; administration, logging and
locking sockets remain restricted. There is no libvirt TCP listener. Accounts
authorized before the node-device and network-filter daemons were added need
`virt-manager-setup USER` run again; until then host-device lists fail with a
permission error.
To revoke access, run `virt-manager-setup --revoke USER` as root, then end that
user's sessions and management connections so cached credentials are removed.
Other authorized users and running guests are not stopped by revocation.

## Guests and storage

Create guests from readable installation media or existing raw/qcow2 disks.
Firmware follows the operating system: guests whose OS database entry requires
UEFI (for example Windows 11) get UEFI and an emulated TPM 2.0; others default
to SeaBIOS. Tick *Customize configuration before install* to choose UEFI or
Secure Boot under **Overview → Firmware** or to add **TPM → Emulated** for any
guest; see [libvirt](libvirt.md#uefi-secure-boot-and-virtual-tpm).
Use an existing OpenWrt bridge, normally `br-lan`; this integration does not
create a second DHCP server. Libvirt NAT/isolated virtual networks (`virbr*`)
are intentionally not built. Default directory storage is `/srv/libvirt/images`,
while an existing pool remains authoritative. Mount external storage before
its pools and autostart guests. See [libvirt](libvirt.md) for persistence,
permission and shutdown policy.

New graphical guests use the available VirtIO video and local SPICE console;
3D starts disabled. Prepare guest VirtIO drivers before selecting VirtIO disk,
network or video devices. Clipboard and dynamic resizing require guest-side
spice-vdagent. A guest OS must enable its serial console or respond to ACPI
shutdown for those functions to work.

**Add Hardware → PCI Host Device** and **USB Host Device** list the host's
devices through the node-device daemon. Read
[libvirt](libvirt.md#pci-and-usb-passthrough) first: PCI passthrough needs an
active IOMMU, and a NIC that OpenWrt uses must never be passed through.
Network filters are set in the interface XML (**NIC → XML**); see
[libvirt](libvirt.md#network-filters).

## SPICE and graphics

`libmesa-virtualization` supplies the selected Mesa/GLVND runtime; QEMU's
`QEMU_OPENGL` and `QEMU_VIRGLRENDERER` options must match the desired features.
For local SPICE GL, stop the guest, enable VirtIO 3D, choose SPICE OpenGL with
Listen None, and select an accessible `/dev/dri/renderD*` node. Both the host
QEMU process and viewer need the appropriate GPU access and graphics runtime.

A visible installer establishes a 2D console, not accelerated guest rendering.
Windows 3D and particular guest drivers need separate compatibility tests.
SPICE GL uses local UNIX sockets/file descriptors; remote desktop access uses
GNOME RDP or Sunshine/Moonlight to view the same host session.

`virt-manager-setup` manages the required administrator/render group access.
Restart the user's sessions after group changes. Do not solve access failures
by making render or input devices writable to everyone.

## Build, upgrades and evidence

```sh
make package/custom/virt-manager/compile V=s
python3 scripts/build-and-publish.py build-only -j12 V=s
```

Use matching signed APKs from `bin/systemd`. Back up `/etc/libvirt`,
`/srv/libvirt`, other guest storage and users' settings separately; firmware
configuration backups do not contain full guest disks.

[Libvirt validation](libvirt-validation.md),
[VM manager validation](virt-manager-validation.md) and
[SPICE/VirGL validation](virtio-spice-validation.md) contain dated component
results. Current host-session behavior is covered by [GNOME validation](gnome-desktop-validation.md).
Documentation changes do not rerun those tests.
