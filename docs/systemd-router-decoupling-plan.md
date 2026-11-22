# OpenWrt native systemd 纯路由构建与应用解耦

状态：纯路由配置、包依赖解耦、隔离构建与纯路由 KVM 验收已完成（2026-11-19），详见 [验证记录](systemd-router-decoupling-validation.md)。可选应用（GNOME 无/含 Flatpak、Podman、Samba、libvirt/virt-manager）的运行时回归测试与实体链路 PPPoE 验收待单独执行；生产发布和实体设备操作未执行。

## 目标与范围

从当前 x86_64/glibc/APK 树独立构建一个有线纯路由镜像。它应能以 systemd 为 PID 1 冷启动，初始化 LAN，完成 PPPoE 拨号，并为 LAN 客户端提供 DHCP、DNS 和 NAT。GNOME、Flatpak、Podman、Distrobox、Samba 和虚拟化分别选择，保留实际运行所需的单向依赖。

本次范围是构建配置和包依赖。USB 安装器的离线组件选择另见 [安装器可选组件方案](installer-components-plan.md)。现有完整桌面配置、正常 systemd 启动与原生 `failsafe=true` 恢复路径（按 [systemd 单 init 方案](systemd-only-plan.md) 现行基线）、已安装设备的配置和 APK 顶层选择继续受支持。

## 审查发现

- **启动链**。GRUB 正常项传入 `openwrt.init=systemd`。OpenWrt `/sbin/init` 先执行 preinit 和 overlay 挂载，随后通过 `openwrt-systemd-prepare` 检查 merged /usr、/run、journald 兼容标记，并在存在内核代际元数据时执行 `kernelctl prepare`。检查失败会回退到 procd，因此验收必须直接检查 PID 1。当前 `systemd-openwrt` 拉入 systemd、udev、procd、ubus、D-Bus、polkit、PAM 版 OpenSSH、兼容 logd 等，桌面可选不改变这组配方依赖。 [启动说明](systemd.md) · [启动预检](../package/system/systemd-openwrt/files/openwrt-systemd-prepare)
- **网络链**。`openwrt-procd.service` 提供 ubus service API 和热插拔处理，`openwrt-services.service` 按顺序执行 rc 脚本。netifd 由 `/etc/init.d/network` 注册，PPPoE 脚本加载 PPP 内核模块并调用带 `pppoe.so` 的 pppd。WAN 拨号与 LAN 转发分别验收。默认有静态 LAN 时，`network-online.target` 的等待以 LAN 等静态接口为主。 [netifd rc 脚本](../package/network/config/netifd/files/etc/init.d/network) · [PPPoE 脚本](../package/network/services/ppp/files/ppp.sh) · [就绪语义](systemd.md#network-readiness)
- **Kconfig 反向选包**。在现有桌面配置里只取消应用主包，归一化后 `openwrt-desktop`、`gnome-shell`、`podman`、`flatpak` 和 `samba4-server` 被重新选入。桌面音频、输入法、AppImage 和 virt-manager 都会拉回桌面，portal 会选回 Flatpak，Podman/Samba 的 LuCI 插件会拉回各自运行包。
- **独立配置试算**。对新 seed 使用现有生成的 Kconfig 元数据执行 `scripts/config/conf --fatalrecursive`，输入、输出均放在内存文件描述符中。配置保留 systemd、procd、ubus、netifd、firewall4、dnsmasq-full、IPv6 和 PPPoE 链，得到 221 个取值为 `y` 的 `PACKAGE_*` 项。GNOME、Flatpak、Podman、Distrobox、Samba、wsdd2、Avahi、libvirt、QEMU 和安装器均未入选。该次试算未选 LuCI，221 是试算计数。空 seed 需要同时设置 `DEVEL=y`、`TOOLCHAINOPTS=y` 和 `LIBC_USE_GLIBC=y`，否则选择会回到 musl，`OPENWRT_SYSTEMD` 随之失效。 [systemd Kconfig](../config/Config-build.in) · [工具链 Kconfig](../toolchain/Config.in)
- **镜像默认值**。普通 combined 镜像复制根目录 `files/`；安装器 ISO 只复制 Git 跟踪的默认文件。当前本地 overlay 含 PPPoE WAN、Podman 防火墙区和 Passwall include。干净通用 x86 镜像在识别到 WAN 时默认用 DHCP。测试使用干净默认值，在客体注入 WAN 端口、合成账号密码和需要的 VLAN，避免继承或记录现场凭据。 [combined 组装](../package/Makefile) · [ISO 组装](../target/linux/x86/image/Makefile) · [WAN 默认值](../package/base-files/files/lib/functions/uci-defaults.sh)

## 实施顺序与结果

1. **已完成**：新增 [configs/x86-64-systemd-router.config](../configs/x86-64-systemd-router.config)。从 x86_64 generic 默认值和顶层包开始，保留 UEFI squashfs、正常 systemd 与原生 `failsafe=true` 恢复入口（与 [systemd-only-plan.md](systemd-only-plan.md) 一致）、签名 APK、kernelctl、SSH（含 `openssh-keygen`）、多用户基础工具（`sudo` 与不含 `shadow-login` 的 `shadow-*`）、LuCI（含中文语言包）、dnsmasq-full、odhcp6c/odhcpd-ipv6only、firewall4、ppp、ppp-mod-pppoe、curl、tcpdump 以及 kmod、kmod-nvme、kmod-r8169、kmod-igc、kmod-igb、kmod-e1000e 和 kmod-e1000。显式关闭 video-support、普通 dnsmasq、dropbear、shadow-all/shadow-login 和安装器 ISO。同时修复 [package/utils/busybox/Makefile](../package/utils/busybox/Makefile) 在关闭 `BUSYBOX_CUSTOM` 时漏掉 `BUSYBOX_DEFAULT_PAM:libpam` 的依赖问题（`PKG_RELEASE:=16`）。
2. **已完成**：拆开 GNOME 与 Flatpak 运行时。修改 [package/custom/xdg-desktop-portal/Makefile](../package/custom/xdg-desktop-portal/Makefile) 从固定版本、SHA-256 校验的 `flatpak-1.18.4.tar.xz` 提取 `data/org.freedesktop.portal.Flatpak.xml`，通过 Meson 的 `-Dflatpak-interfaces-dir=` 传入目录，保留 Flatpak 接口代码生成和 Bubblewrap 沙箱，移除 `+flatpak` 运行时依赖，并将 `PKG_RELEASE` 升至 `5`（避开 `configs/apk-elf-rebuilds.mk` 已保留的 `1.22.1-r4`）。新增 [configs/gnome-desktop-core.config](../configs/gnome-desktop-core.config) 用于在纯路由基线上无 Flatpak 组合 GNOME 与 RDP；`openwrt-flatpak` 显式引入 Flatpak 运行时。
3. **已完成**：整理容器与 NAS 的顶层选择。新增 [configs/podman.config](../configs/podman.config)（`podman` + `openwrt-podman-rootless` + `luci-app-podman`）与 [configs/distrobox.config](../configs/distrobox.config)（通过 `openwrt-podman-rootless` 单向依赖 Podman）；沿用 [configs/samba4.config](../configs/samba4.config) 及 `SAMBA4_SERVER_WSDD2`/`SAMBA4_SERVER_AVAHI` 可选开关、`nas.slice` 与 native units；保留完整桌面配置中的现有功能选择。
4. **已完成**：拆开虚拟化与桌面。新增无头虚拟化片段 [configs/virt-headless.config](../configs/virt-headless.config)（`libvirt-daemon` + `virsh` + `virt-install` + `qemu-x86_64-softmmu` + `luci-app-qemu`）。将普通用户校验逻辑内联到 [package/custom/virt-manager/files/virt-manager-setup](../package/custom/virt-manager/files/virt-manager-setup)，移除对 `desktop-common.sh` 与 `+openwrt-desktop` 的依赖，显式补足 `+shadow-usermod`，并将 [package/custom/virt-manager/Makefile](../package/custom/virt-manager/Makefile) 的 `PKG_RELEASE` 升至 `5`。
5. **已完成（隔离验收）**：在 `/srv/openwrt-validation/systemd-router-decoupling-validation-20261119/checkout` 使用匹配的 feed 修订与受跟踪的 11 个默认 overlay 文件独立构建纯路由固件，未修改主工作区 `.config`、`bin/systemd` 或个人 overlay；未发布 LAN APK feed，也未操作实体设备。详细验证记录与未覆盖边界见 [systemd-router-decoupling-validation.md](systemd-router-decoupling-validation.md)。

## 验收与证据边界

| 类别 | 验收内容 |
| --- | --- |
| 配置与产物 | 对纯路由、GNOME 无 Flatpak、GNOME 加 Flatpak、Podman 无 Distrobox、Distrobox、Samba、无桌面虚拟化做严格归一化。检查对应实际 APK 清单、依赖闭包和启动链接，确认所选功能存在，未选组件未被间接装回。 |
| 精简路由镜像 | 冷启动 KVM，确认 PID 1 是 systemd、overlay 可写、procd/ubus/netifd 正常、恢复入口可启动。先复用 DHCP 双 VM 测试，再用隔离以太网段和测试 PPPoE AC 验证发现、认证、默认路由、断线重拨。用独立 LAN 客户端验证 DHCP、DNS、转发、NAT。 |
| 应用回归 | 验证无 Flatpak 的 GNOME 文件选择、屏幕共享与完整配置 RDP，启用 Flatpak 后验证普通用户应用及 portal。验证无桌面 Podman、Samba、libvirt，及 virt-manager 的授权、连接和撤销。 |
| APK 与内核 | 在独立环境分别验证现有完整镜像和新纯路由镜像的签名 APK 升级。检查既有 APK world、UCI、功能选择和 `kernelctl check`。记录精确镜像 SHA256、清单及测试结果。物理 NIC、线路 VLAN 和真实 ISP PPPoE 单独验收。 |

2026-11-19 已在独立 checkout 完成纯路由配置与依赖解耦实现、隔离镜像构建、Kconfig 全矩阵归一化、解耦包独立编译打包、双 VM DHCP/DNS/NAT/LuCI 验收，以及新增的 [PPPoE AC / failsafe 三 VM 脚本](../scripts/tests/test-systemd-router-pppoe-vm.py) 验收，结果见 [纯路由与解耦验证记录](systemd-router-decoupling-validation.md)。应用回归（GNOME 无/含 Flatpak、无桌面 Podman/Samba/libvirt 及 virt-manager 运行时）、完整镜像签名 APK 升级回归和物理线路 PPPoE/VLAN 验收仍作为后续独立验收项保留。
