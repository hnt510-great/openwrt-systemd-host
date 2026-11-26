# Virtual Machine Manager on the systemd desktop

This integration targets x86_64/glibc with native systemd. It adds a GTK 3
Wayland application to the shared desktop session (GNOME 51 or KDE Plasma 6.8.3;
see [gnome-desktop.md](gnome-desktop.md) and [kde-plasma.md](kde-plasma.md)).
The client connects to the local modular libvirt daemons using `qemu:///system`.

## Setup and authorization

Create an ordinary desktop account and configure the desktop as documented
in [gnome-desktop.md](gnome-desktop.md) or [kde-plasma.md](kde-plasma.md). No
human account or authentication key is built into the firmware. As root,
explicitly authorize that existing account:

    virt-manager-setup alice
    /etc/init.d/desktop restart

The *Virtual Machine Manager* entry in the desktop application launcher starts it
as the desktop account.
You can also run `/usr/libexec/virt-manager-launch` from its terminal.
The desktop has its own D-Bus session; dconf stores preferences in the user's
home. The application is never started automatically and does not run via sudo.

The `libvirt-admin` group grants full read/write management of local QEMU,
storage and secret resources. This is a trusted-administrator role with
privileges comparable to root, rather than a restricted VM operator role.
Only add users you trust to administer the host.

Remove authorization as root:

    virt-manager-setup --revoke alice
    /etc/init.d/desktop restart

Also end the user's other login sessions and VM management applications to
remove their old group credentials and established libvirt connections.
Other authorized accounts retain their membership. Changing authorization
does not stop running virtual machines.

Only the read/write and read-only client UNIX sockets of virtqemud,
virtstoraged, virtsecretd, virtnodedevd and virtnwfilterd are granted group
access after setup. Accounts authorized before the node-device and
network-filter daemons were added need `virt-manager-setup USER` run again;
until then host-device lists fail with a permission error. Daemon
administration, log and lock sockets retain root-only access. There is no
libvirt TCP listener or polkit authentication agent in this integration.
If startup fails, the launcher shows the connection error and a Retry button.

## Creating guests

Use the creation wizard to install from an existing readable Linux ISO or
import a raw/qcow2 disk. Defaults are qcow2 storage, SPICE with a local socket and a VirtIO
video device. Firmware follows the operating system: guests whose OS database
entry requires UEFI (for example Windows 11) get UEFI and an emulated TPM 2.0;
others default to SeaBIOS. Tick *Customize configuration before install* to
choose UEFI or Secure Boot under **Overview → Firmware** or to add
**TPM → Emulated** for any guest; see
[libvirt.md](libvirt.md#uefi-secure-boot-and-virtual-tpm). OpenGL and 3D acceleration are initially disabled. VNC remains
available on loopback. Use the desktop's LAN RDP sharing (`gnome-remote-desktop`
or `krdp`) or Sunshine/Moonlight for remote desktop access. Existing guests and
saved user preferences are not migrated.

The network defaults to `br-lan`. For a different existing OpenWrt bridge,
enter its name in the bridge field. OpenWrt continues to own bridges, DHCP
and firewall policy. The package does not create virbr0 or a second DHCP
server. Choose guest memory and disk sizes appropriate for the host.

New default storage uses `/srv/libvirt/images`. An existing default storage
pool remains authoritative. A directory pool on an external disk can be
configured in the storage UI. The filesystem must be mounted before that
pool and any autostart guests; see [libvirt.md](libvirt.md) for persistence,
mount dependencies and backup guidance. ISO directories need traversal
permissions and the libvirt-qemu account needs read access to the ISO.

**Add Hardware → PCI Host Device** and **USB Host Device** list the host's
devices through the node-device daemon. Read
[libvirt.md](libvirt.md#pci-and-usb-passthrough) first: PCI passthrough needs an
active IOMMU, and a NIC that OpenWrt uses must never be passed through.
Network filters are set in the interface XML (**NIC → XML**); see
[libvirt.md](libvirt.md#network-filters).

Libvirt NAT/isolated virtual networks (`virbr*`) are intentionally not built;
guests attach to OpenWrt bridges. Remote-host management is not supported.
Guest shutdown requires a guest OS that responds to ACPI shutdown; serial
console access requires the guest OS to enable that console.

## Build and upgrade

Select `virt-manager` and `virt-install`, normalize the configuration, then
build the package dependency graph before building the complete firmware:

    make defconfig
    make package/custom/virt-manager/compile -j3 V=s
    make -j3 V=s

As of `virt-manager` `5.1.0-r5`, `virt-manager` no longer depends on
`openwrt-desktop`: `virt-manager-setup` validates ordinary user accounts
directly without sourcing `/usr/libexec/desktop-common.sh` and `virt-manager`
explicitly depends on `shadow-usermod`. For headless virtualization without
`virt-manager` or GNOME, merge `configs/virt-headless.config` onto
`configs/x86-64-systemd-router.config` (see
[systemd-router-decoupling-validation.md](systemd-router-decoupling-validation.md)).

New package definitions live under `package/custom`. Existing matching GLib,
Pango, HarfBuzz and GdkPixbuf packages add the required runtime metadata.
GIR scanning uses host tools, target headers/libraries, and an explicit target
glibc executable runner. Do not substitute Debian/Alpine binaries or host
GIR files for target metadata.

Use the signed APKs and EFI image from the same build under `bin/systemd`.
Keep libvirt definitions, guest disks and persistent state backed up as
specified in [libvirt.md](libvirt.md); firmware backup alone is insufficient.
Back up users' home directories separately, including their dconf settings.
Account/group files and the explicit socket authorization drop-ins are
included in the OpenWrt configuration preservation rules.

Runtime and complete-image verification is recorded in
[virt-manager-validation.md](virt-manager-validation.md), including the exact
image checksum and test limits.

## 安装后的快速操作

以 root 创建自己的普通账号、设置密码并配置桌面（GNOME 或 KDE Plasma）后，显式授权：

```sh
desktop-setup USER
virt-manager-setup USER
/etc/init.d/desktop restart
```

在桌面应用列表中打开“Virtual Machine Manager”。`libvirt-admin` 成员可以管理
本机虚拟机、存储和 secret，权限接近 root，只应授权可信管理员。固件不预置
人类账号或密码。撤销授权使用 `virt-manager-setup --revoke USER`，然后退出
该用户的桌面、SSH 和管理器会话，重新登录以刷新组身份。

新建向导选择 ISO 安装或导入现有 raw/qcow2 磁盘，网络选择已有桥，默认
`br-lan`。ISO 不在 osinfo 数据库中时，取消自动识别并选择相近系统；本次
Alpine 3.24 测试选择 Generic Linux 2024。确认主机可用内存和存储空间后再
创建客体。目录存储池可在“连接详情 → Storage”中管理。

Windows 11 等要求 UEFI 的系统会自动使用 UEFI（Secure Boot、已登记微软密钥）
和模拟 TPM 2.0；其他系统默认 SeaBIOS，可在“安装前自定义配置”中切换固件
或添加 TPM。“添加硬件 → PCI/USB 主机设备”可直通主机设备：PCI 直通需要
启用 IOMMU，切勿直通 OpenWrt 正在使用的网卡。已在本功能之前授权的账号需
重新运行 `virt-manager-setup USER`。详见 [libvirt.md](libvirt.md)。

新建图形控制台默认使用本地 SPICE socket 和 VirtIO 显卡，3D 默认关闭；已有
VNC 客体继续可用。串口控制台在“View → Consoles”
中选择，客体须启用串口 getty。自动启动在客体的 Boot Options 中设置。
普通用户终端使用 `virsh -c qemu:///system`，避免连接到用户会话实例。

升级或重装系统前备份 `/etc/libvirt`、`/srv/libvirt`、其他存储池和用户 home 中的
dconf 配置。OpenWrt 配置备份不包含完整客体磁盘和 `/home`。整机固件替换请使用安装
介质（[installer-iso.md](installer-iso.md)）或离线磁盘写盘；日常软件包升级通过签名
LAN APK feed 执行 `apk upgrade`。

## SPICE, VirtIO and OpenGL

The virtualization Mesa provider (`libmesa-virtualization`) uses GLVND for EGL,
GLES, desktop OpenGL, GLX (for Xwayland/AppImage), and Vulkan ICDs (`intel`,
`intel_hasvk`, `virtio`). Its `50_mesa.json` selects `libEGL_mesa.so.0`. Both
the dispatch libraries and vendor configuration are required for VirGL;
EGL/GLES alone is insufficient.

The local CPU panel supports host-passthrough with KVM. Disk bus VirtIO and
NIC model VirtIO are available; the NIC uses the existing OpenWrt bridge.
The creation wizard defaults to VirtIO video when QEMU reports support,
including when the OS database has no matching VirtIO-GPU entry. Guests must
supply the corresponding VirtIO drivers; for Windows, prepare those drivers
before selecting VirtIO disk, NIC or video.

To enable 3D, shut down the guest, select **Video → Virtio → 3D acceleration**,
then **Display Spice → Listen type None → OpenGL** and choose an existing
`/dev/dri/renderD*` node via libvirt's `virtnodedevd` udev enumeration. Save both changes before starting. A missing
node, denied access or EGL initialization failure remains a visible startup
error; the application does not silently disable acceleration.

SPICE GL is local and uses UNIX sockets/file descriptors through libvirt,
including the Listen None mode. It is not a LAN SPICE server; remote desktop
access continues through LAN RDP or Sunshine/Moonlight. Both QEMU and the
desktop client use EGL.

Windows Setup and the standard VirtIO Windows display driver provide 2D
output. Enabling the host renderer or the VM's 3D checkbox does not install
an accelerated Windows driver. Experimental Windows 3D drivers require a
separate compatibility and rendering test; a visible installer is only a
2D console check.

`virt-manager-setup USER` grants render-group membership as well as VM
management. Revoke removes render membership only if this helper added it;
pre-existing membership remains. Restart all of the user's sessions to refresh
groups. `accel-support` allocates the render group and `systemd-udevd` manages
DRM/render device node permissions (`root:render` `0660` for `renderD*`), while
libvirt preparation repairs already present render nodes at service start.
Display card nodes and input devices do not receive broader permissions.

The selected `libmesa-virtualization` package contains Intel iris/crocus/i915,
virtual VirtIO-GPU virgl and software softpipe in one Mesa build. Select it
instead of other `libmesa-*` OpenGL providers: their common EGL/GBM/Gallium
files overlap. Software rendering remains available but is not evidence of
hardware acceleration. The source package supports selecting other providers
for other firmware configurations.

QEMU build options are `QEMU_UI_SPICE`, `QEMU_OPENGL` and
`QEMU_VIRGLRENDERER`; VirGL requires OpenGL. The firmware includes spice-gtk
with SpiceClientGLib and SpiceClientGtk Python introspection metadata. New
SPICE guests do not automatically receive unsupported sound or USB redirection
devices. SPICE clipboard/resizing needs a guest-side spice-vdagent; no guest
agent is installed into a guest automatically.

See [libvirt.md](libvirt.md#graphics-examples) for XML and CLI examples, and
[libvirt-uefi-passthrough-validation.md](libvirt-uefi-passthrough-validation.md),
[libvirt-audio-validation.md](libvirt-audio-validation.md), and
[spice-egl-build-validation.md](spice-egl-build-validation.md) for current
build and runtime evidence.
