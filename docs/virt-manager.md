# Virtual Machine Manager on the Weston desktop

This integration targets x86_64/glibc with native systemd. It adds a GTK 3
Wayland application alongside the existing Weston terminal desktop. The
client connects to the local modular libvirt daemons using `qemu:///system`.

## Setup and authorization

Create an ordinary desktop account and configure the desktop as documented
in [desktop.md](desktop.md). No human account or authentication key is built
into the firmware. As root, explicitly authorize that existing account:

    virt-manager-setup alice
    /etc/init.d/desktop restart

The new panel icon starts Virtual Machine Manager as the desktop account.
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
virtstoraged and virtsecretd are granted group access after setup. Daemon
administration, log and lock sockets retain root-only access. There is no
libvirt TCP listener or polkit authentication agent in this integration.
If startup fails, the launcher shows the connection error and a Retry button.

## Creating guests

Use the creation wizard to install from an existing readable Linux ISO or
import a raw/qcow2 disk. Defaults are SeaBIOS, qcow2 storage and a local VNC
console. The VNC connection remains inside the host; use the existing TLS
Weston desktop mirror for remote desktop access.

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

UEFI guest firmware, SPICE, device passthrough, libvirt NAT network creation,
and remote-host management are outside the supported first release.
Guest shutdown requires a guest OS that responds to ACPI shutdown; serial
console access requires the guest OS to enable that console.

## Build and upgrade

Select `virt-manager` and `virt-install`, normalize the configuration, then
build the package dependency graph before building the complete firmware:

    make defconfig
    make package/custom/virt-manager/compile -j3 V=s
    make -j3 V=s

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

以 root 创建自己的普通账号、设置密码并配置 Weston 桌面后，显式授权：

```sh
desktop-setup USER
virt-manager-setup USER
/etc/init.d/desktop restart
```

点击 Weston 面板的虚拟机图标即可打开管理器。`libvirt-admin` 成员可以管理
本机虚拟机、存储和 secret，权限接近 root，只应授权可信管理员。固件不预置
人类账号或密码。撤销授权使用 `virt-manager-setup --revoke USER`，然后退出
该用户的桌面、SSH 和管理器会话，重新登录以刷新组身份。

新建向导选择 ISO 安装或导入现有 raw/qcow2 磁盘，网络选择已有桥，默认
`br-lan`。ISO 不在 osinfo 数据库中时，取消自动识别并选择相近系统；本次
Alpine 3.24 测试选择 Generic Linux 2024。确认主机可用内存和存储空间后再
创建客体。目录存储池可在“连接详情 → Storage”中管理。

图形控制台通过宿主回环地址上的 VNC 连接；串口控制台在“View → Consoles”
中选择，客体须启用串口 getty。自动启动在客体的 Boot Options 中设置。
普通用户终端使用 `virsh -c qemu:///system`，避免连接到用户会话实例。

升级前备份 `/etc/libvirt`、`/srv/libvirt`、其他存储池和用户 home 中的 dconf
配置。OpenWrt 配置备份不包含完整客体磁盘。原生 systemd 下实际刷写仍须
先进入 GRUB 的 procd recovery；不要用单包升级替代已验证的完整固件。
