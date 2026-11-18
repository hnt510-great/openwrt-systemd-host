# OpenWrt native systemd 纯路由构建与应用解耦

状态：方案已确认。源码审查、Kconfig 试算和相关宿主机测试已完成。纯路由配置和包依赖改动待实现，精简固件待构建和验收。

## 目标与范围

从当前 x86_64/glibc/APK 树独立构建一个有线纯路由镜像。它应能以 systemd 为 PID 1 冷启动，初始化 LAN，完成 PPPoE 拨号，并为 LAN 客户端提供 DHCP、DNS 和 NAT。GNOME、Flatpak、Podman、Distrobox、Samba 和虚拟化分别选择，保留实际运行所需的单向依赖。

本次范围是构建配置和包依赖。USB 安装器的离线组件选择另见 [安装器可选组件方案](installer-components-plan.md)。现有完整桌面配置、正常启动与恢复路径、已安装设备的配置和 APK 顶层选择继续受支持。

## 审查发现

- **启动链**。GRUB 正常项传入 `openwrt.init=systemd`。OpenWrt `/sbin/init` 先执行 preinit 和 overlay 挂载，随后通过 `openwrt-systemd-prepare` 检查 merged /usr、/run、journald 兼容标记，并在存在内核代际元数据时执行 `kernelctl prepare`。检查失败会回退到 procd，因此验收必须直接检查 PID 1。当前 `systemd-openwrt` 拉入 systemd、udev、procd、ubus、D-Bus、polkit、PAM 版 OpenSSH、兼容 logd 等，桌面可选不改变这组配方依赖。 [启动说明](systemd.md) · [启动预检](../package/system/systemd-openwrt/files/openwrt-systemd-prepare)
- **网络链**。`openwrt-procd.service` 提供 ubus service API 和热插拔处理，`openwrt-services.service` 按顺序执行 rc 脚本。netifd 由 `/etc/init.d/network` 注册，PPPoE 脚本加载 PPP 内核模块并调用带 `pppoe.so` 的 pppd。WAN 拨号与 LAN 转发分别验收。默认有静态 LAN 时，`network-online.target` 的等待以 LAN 等静态接口为主。 [netifd rc 脚本](../package/network/config/netifd/files/etc/init.d/network) · [PPPoE 脚本](../package/network/services/ppp/files/ppp.sh) · [就绪语义](systemd.md#network-readiness)
- **Kconfig 反向选包**。在现有桌面配置里只取消应用主包，归一化后 `openwrt-desktop`、`gnome-shell`、`podman`、`flatpak` 和 `samba4-server` 被重新选入。桌面音频、输入法、AppImage 和 virt-manager 都会拉回桌面，portal 会选回 Flatpak，Podman/Samba 的 LuCI 插件会拉回各自运行包。
- **独立配置试算**。对新 seed 使用现有生成的 Kconfig 元数据执行 `scripts/config/conf --fatalrecursive`，输入、输出均放在内存文件描述符中。配置保留 systemd、procd、ubus、netifd、firewall4、dnsmasq-full、IPv6 和 PPPoE 链，得到 221 个取值为 `y` 的 `PACKAGE_*` 项。GNOME、Flatpak、Podman、Distrobox、Samba、wsdd2、Avahi、libvirt、QEMU 和安装器均未入选。该次试算未选 LuCI，221 是试算计数。空 seed 需要同时设置 `DEVEL=y`、`TOOLCHAINOPTS=y` 和 `LIBC_USE_GLIBC=y`，否则选择会回到 musl，`OPENWRT_SYSTEMD` 随之失效。 [systemd Kconfig](../config/Config-build.in) · [工具链 Kconfig](../toolchain/Config.in)
- **镜像默认值**。普通 combined 镜像复制根目录 `files/`；安装器 ISO 只复制 Git 跟踪的默认文件。当前本地 overlay 含 PPPoE WAN、Podman 防火墙区和 Passwall include。干净通用 x86 镜像在识别到 WAN 时默认用 DHCP。测试使用干净默认值，在客体注入 WAN 端口、合成账号密码和需要的 VLAN，避免继承或记录现场凭据。 [combined 组装](../package/Makefile) · [ISO 组装](../target/linux/x86/image/Makefile) · [WAN 默认值](../package/base-files/files/lib/functions/uci-defaults.sh)

## 实施顺序

1. 新增 `configs/x86-64-systemd-router.config`。从 x86_64 generic 默认值和顶层包开始，保留 UEFI squashfs、正常 systemd/恢复 procd 启动、签名 APK、kernelctl、SSH、LuCI、dnsmasq-full、odhcp6c/odhcpd-ipv6only、firewall4、ppp 和 ppp-mod-pppoe。保留实际需要的磁盘和网卡支持。试算显式选择了 kmod、kmod-nvme、kmod-r8169、kmod-igc、kmod-igb、kmod-e1000e 和 kmod-e1000。x86 7.3 内核配置已有 VirtIO 网卡和 802.1Q 支持。显式关闭默认选入的 video-support、普通 dnsmasq 和安装器 ISO。安装匹配 feeds 后生成 Kconfig 元数据，用严格归一化和最终 APK 清单验证结果。
2. 拆开 GNOME 与 Flatpak 运行时。让 `xdg-desktop-portal` 从固定版本、哈希校验的 Flatpak 源码归档提取 `data/org.freedesktop.portal.Flatpak.xml`。当前源码基线是 Flatpak 1.18.4。在 portal 的构建目录放置 XML，通过 Meson 的 `flatpak-interfaces-dir` 传入目录，保留 Flatpak 接口代码生成和 Bubblewrap 图像/音频沙箱，移除 portal 的 `+flatpak` 运行时依赖。由 `openwrt-flatpak` 显式引入运行时，完整桌面保留现有 RDP。
3. 整理容器与 NAS 的顶层选择。Podman 可单独入镜；Distrobox 继续通过 `openwrt-podman-rootless` 使用 Podman。容器 LuCI 插件、翻译包与 Podman 防火墙配置随容器功能选择。Samba server 与其 LuCI 插件和翻译包一起选择，wsdd2 与 Avahi 按发现需求选择。沿用已存在的 Samba、wsdd2、Avahi native units 和 `nas.slice`。保留完整配置中的现有功能选择。
4. 拆开虚拟化与桌面。QEMU、libvirt 和现有 LuCI 管理支持无桌面构建。`virt-manager-setup` 目前引用 `desktop-common.sh` 的普通账号校验。将该校验移出桌面脚本依赖后移除 virt-manager 的 `+openwrt-desktop`。保留 UID/GID、主目录、登录 shell、账号密码状态检查以及现有 libvirt socket 权限、render 授权标记和撤销语义。
5. 在独立 checkout 使用匹配的 feed 修订和受跟踪的默认 overlay 构建。隔离配置、staging 和输出，保留生产工作区以及完整桌面产物。保留包名、UCI、服务入口和已安装系统的 APK `world`。修改过的 APK 配方提高 `PKG_RELEASE`。纯路由构建产物使用独立验收目录，生产发布和设备操作单独授权。

## 验收与证据边界

| 类别 | 验收内容 |
| --- | --- |
| 配置与产物 | 对纯路由、GNOME 无 Flatpak、GNOME 加 Flatpak、Podman 无 Distrobox、Distrobox、Samba、无桌面虚拟化做严格归一化。检查对应实际 APK 清单、依赖闭包和启动链接，确认所选功能存在，未选组件未被间接装回。 |
| 精简路由镜像 | 冷启动 KVM，确认 PID 1 是 systemd、overlay 可写、procd/ubus/netifd 正常、恢复入口可启动。先复用 DHCP 双 VM 测试，再用隔离以太网段和测试 PPPoE AC 验证发现、认证、默认路由、断线重拨。用独立 LAN 客户端验证 DHCP、DNS、转发、NAT。 |
| 应用回归 | 验证无 Flatpak 的 GNOME 文件选择、屏幕共享与完整配置 RDP，启用 Flatpak 后验证普通用户应用及 portal。验证无桌面 Podman、Samba、libvirt，及 virt-manager 的授权、连接和撤销。 |
| APK 与内核 | 在独立环境分别验证现有完整镜像和新纯路由镜像的签名 APK 升级。检查既有 APK world、UCI、功能选择和 `kernelctl check`。记录精确镜像 SHA256、清单及测试结果。物理 NIC、线路 VLAN 和真实 ISP PPPoE 单独验收。 |

本轮已运行 `scripts/tests/test-network-wait-online.py`（14 项）、`test-systemd-udev-boundary.py`（3 项）和 `test-nas-systemd.py`（8 项），均通过。已有的 [完整镜像 VM 记录](auxiliary-systemd-validation.md) 和 [实体 PPPoE 记录](systemd-udev-boundary-validation.md) 属于既有镜像。现有 [双 VM 脚本](../scripts/test-image-network.py) 在 WAN 使用 DHCP，PPPoE AC 场景待补充。接手从独立 checkout 的配置实现与清单验证开始。
