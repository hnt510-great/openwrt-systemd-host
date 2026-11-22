# OpenWrt Systemd Host

**简体中文** | [English](README.en.md)

<img width="1931" height="1085" alt="Screenshot From 2026-11-05 22-06-51" src="https://github.com/user-attachments/assets/5694540a-657b-4a43-9fa8-368ae20a1a75" />

面向 x86_64 的 OpenWrt 分支：既可以作为独立的**纯路由**系统运行，也可以在同一台机器上按需组合
**GNOME 桌面、容器、虚拟机与原生开发环境**。保留 UCI、LuCI、netifd 与 procd 服务接口，底层采用
**glibc、GCC 15、签名 APK 与原生 systemd**，内核跟踪 **Linux 7.3 主线**。

## 主要特性

- **系统基础与监管**：glibc、GCC 15.3.0、签名 APK（ELF/ucode ABI 约束与中断事务恢复 `apk-resume`）、合并 `/usr`；**systemd 为唯一常规 PID 1**（`procd --systemd=units` 托管瞬态服务，`systemctl openwrt@NAME.service` 桥接，`nas.slice`/`auxiliary.slice` 原生监管，GRUB 保留原生 OpenWrt `failsafe=true` 控制台）
- **可组合配置**：提供独立纯路由配置（`configs/x86-64-systemd-router.config`）与完整桌面配置（`configs/x86-64-systemd-desktop.config`），以及 GNOME 核心、Podman、Distrobox、无头虚拟化、Konsole、Qt6 开发、daed 等可叠加片段
- **桌面与多媒体**：GNOME 51（本地 VT7），RDP 与 Sunshine/Moonlight 共享同一会话；TPM2 密封钥匙环凭据（`systemd-creds`，无 TPM2 时回退明文）、RealtimeKit（`rtkit`）低延迟调度、Fcitx5 中文输入、PipeWire 音频、Firefox ESR 与 Google Chrome，可选 KF6/Konsole 终端栈
- **应用、容器与开发**：Flatpak（同时支持用户级与 D-Bus/polkit 授权的系统级安装及 Xwayland 兼容）、AppImage、Rootless Podman/Quadlet、Distrobox、原生开发工具链（`native-libs-dev`、`kernel-dev-headers`、Qt6 开发包）
- **虚拟化**：QEMU/KVM、libvirt、virt-manager、SPICE/VirGL、OVMF（UEFI/Secure Boot）、`swtpm`（TPM 2.0，支持 Windows 11）、`virtiofsd`、PCI/USB 直通与每虚拟机 nftables 网络过滤
- **路由与运维**：Full cone NAT、dnsmasq nftset netlink 快路径、LAN 发现流量 `notrack`、非特权 `pppd`（`ujail`）、`ttyd` HTTPS、`irqbalance` 网卡 CPU 池；默认 Passwall，可选 daed（eBPF，默认停用）；内置 `uci-history`（Git 版本化配置与定时自动回滚）、`needrestart` 与可选 `router-audit`（默认关闭）
- **安装与滚动升级**：混合 BIOS/UEFI 安装 ISO 支持**离线签名可选组件安装**；LZ4 squashfs 加速滚动镜像打包；内核按批次独立打包（`linux-image-*`）并由 `kernelctl` 管理 GRUB 3 次试启动与回退；发布前自动执行 ELF 类型 ABI 诊断与真实路由器 APK 升级预检

## 构建

需要一台装好 [OpenWrt 构建依赖](https://openwrt.org/docs/guide-developer/build-system/install-buildsystem)
的 Linux 主机；构建安装 ISO 还需要 `xorriso`。主树、feeds 与 Argon 主题仓库均已公开，
可直接通过 HTTPS 克隆，无需登录 GitHub：

```sh
git clone https://github.com/hnt510-great/openwrt-systemd-host.git
cd openwrt-systemd-host
./scripts/feeds update -a     # 同时会检查并更新 package/custom 配方版本
./scripts/feeds install -a
```

新 checkout 可从以下两种基线配置之一开始：

```sh
# 完整桌面 + 虚拟化 + 容器 + 安装 ISO
cp configs/x86-64-systemd-desktop.config .config
# 或独立纯路由（最小原生 systemd 路由基线）
# cp configs/x86-64-systemd-router.config .config

make defconfig
make download
python3 scripts/build-and-publish.py build-only -j12 V=s
```

`build-only` 会预留内核批次号并完成打包，但不发布、不部署。已有工作区请保留自己的 `.config`，
按需用 `scripts/kconfig.pl` 合并 `configs/<功能>.config` 片段（例如 `gnome-desktop-core.config`、
`podman.config`、`distrobox.config`、`virt-headless.config`、`konsole.config`、`qt6-dev.config`、
`daed.config`、`installer-iso.config`）：

```sh
./scripts/kconfig.pl + .config configs/installer-iso.config > .config.new
mv .config.new .config
make defconfig
```

单包构建：

```sh
make package/custom/openwrt-desktop/compile V=s
```

产物位于 `bin/systemd/`。更多说明见 [本地构建](docs/local-build.md) 与 [路由解耦方案](docs/systemd-router-decoupling-plan.md)。

## 安装

### 使用安装 ISO（推荐）

安装器支持 **UEFI 和传统 BIOS** 启动，目标盘建议 16 GB 以上。ISO 内置精简基础系统与**经 `/rom/etc/apk/keys` 校验的离线签名 APK 仓库**，安装时可按需勾选桌面、远程访问、Flatpak、容器、虚拟化、浏览器等组件。

准备一个安装 U 盘和一块独立目标盘，将 ISO 原始写入整个 U 盘（可用 Etcher、Rufus 的 **DD 模式**，或 `dd`；先确认设备名，将 `/dev/REPLACE_USB` 换成实际 U 盘设备，写入会清空该 U 盘）：

```sh
sudo dd if=bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-installer.iso of=/dev/REPLACE_USB bs=4M conv=fsync status=progress
sync
```

1. 从 U 盘启动，选择 **Install OpenWrt**；串口终端选择 **Install OpenWrt (serial console)**。
2. 在英文文本向导中选择目标盘与分区方案：FAT32 引导分区（ESP）、只读 LZ4 squashfs 系统分区，
   可写 `rootfs_data` 默认 ext4（也可选 btrfs 或 xfs），并可附加数据分区。
3. 根据 MAC 地址、驱动和链路状态选择 WAN/LAN 网口，设置网络、防火墙和 root 密码。
   默认 LAN 为 `192.168.1.1/24`；WAN 支持 DHCP、PPPoE、静态地址或不配置。
4. 选择要离线安装的可选组件（向导会按精确 APK 安装体积预检可写分区空间），并可选创建普通用户及配置 GNOME 启动方式。确认摘要后执行安装：
   **所选目标盘会重新分区，原有数据全部清除，不保留原分区或双系统。**
5. 安装完成后移除 U 盘并重启，从目标盘启动；UEFI 安装无需修改 NVRAM 启动项。

虚拟机可将同一个 ISO 挂载为 **SATA CD-ROM**，设置光驱优先启动，并添加独立可写磁盘；
virt-manager 中已验证的安装器显示型号为 **Standard VGA**。安装后弹出 ISO。Rufus ISO 模式和 Ventoy 暂不支持。
详细操作、无人值守 `--answers` 与故障排查见 [USB／光盘安装器](docs/installer-iso.md)。

### 直接写入磁盘镜像

也可在其他系统或 Live 环境中，将 `combined-efi` 镜像直接写入目标盘，再以 **UEFI** 启动（将 `/dev/REPLACE_DISK` 换成实际目标磁盘，写入会清空目标盘）：

```sh
gunzip -c bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz | sudo dd of=/dev/REPLACE_DISK bs=4M conv=fsync status=progress
sync
```

> **关于重装与恢复**：本固件以 systemd 为唯一常规 init，不再提供 `procd recovery` 启动项；`sysupgrade` 仅用于配置备份与恢复（`-b`/`-l`/`-r`）。日常软件与内核更新均通过 APK 完成；需要整盘更换固件时，请使用安装 ISO 或离线写盘后再恢复配置备份。GRUB 中的 `failsafe` 项提供原生 OpenWrt preinit 紧急恢复控制台。

## 首次使用

1. 从 GRUB 默认项启动，确认 `cat /proc/1/comm` 输出 `systemd`。
   通过安装器安装时，使用向导设置的 root 密码；直接写盘后应先在控制台设置 root 密码。
2. 浏览器打开 `https://LAN-IP/`（或 `http://LAN-IP/`）登录 LuCI。安装器默认 LAN 地址为 `192.168.1.1`，
   按需调整 WAN/LAN、DNS 和时区。
3. 首次进入 LuCI 可通过**系统 → 桌面设置向导**创建或选择普通用户，并配置 GNOME/RDP、Moonlight、容器、Flatpak、虚拟机等功能。
   安装器已创建用户并配置 GNOME 时，可直接使用该用户，按需补充远程桌面等设置。
   详见 [桌面设置向导](docs/desktop-setup.md)。

也可以在 root shell 中手动完成（`alice` 换成自己的用户名）：

```sh
useradd -m -U alice && passwd alice && usermod -aG sudo alice
desktop-setup alice                    # 启动 VT7 上的 GNOME（加 --no-autostart 可关闭自启）
desktop-rdp-setup alice                # 设置 RDP 密码，输出证书指纹
desktop-audio-setup alice              # 可选：PipeWire 音频
sunshine-setup alice --capture=portal  # 可选：Moonlight 串流
podman-rootless-setup alice            # 可选：rootless 容器
flatpak-user-setup alice               # 可选：用户级 Flatpak
virt-manager-setup alice               # 可选：本机虚拟机管理
/etc/init.d/desktop restart
```

常用功能入口：

| 功能 | 使用 |
| --- | --- |
| 本地桌面 | 接显示器与键鼠，**Ctrl+Alt+F7** |
| RDP | `LAN-IP:3389`，用户名 `alice`，密码为 RDP 密码 |
| Moonlight | 先在 `https://LAN-IP:47990` 设置 Sunshine 账号，再在 Moonlight 中 PIN 配对 |
| 容器 / 虚拟机 | `podman`、LuCI **服务 → Rootless Podman**；virt-manager 连接 `qemu:///system` |
| 代理 | LuCI **服务 → Passwall** 填写节点；切换 daed 见 [daed](docs/daed.md) |
| Full cone NAT | LuCI **网络 → 防火墙 → 常规设置** 勾选 |
| 配置历史 / 回滚 | LuCI **系统 → 配置历史** 或 `uci-history`（支持定时事务自动回滚） |
| 重启建议 | LuCI **系统 → 需要重启** 或 `needrestart` |

## 升级

设备通过构建机发布的签名 LAN APK 源进行用户态与内核滚动升级。构建机按
[LAN APK feeds](docs/lan-apk-feeds.md) 发布后，在设备的 `/etc/lan-apk-feeds.conf`
中填写真实 `base_url`，然后：

```sh
lan-apk-feeds-sync
apk update
apk upgrade --simulate   # 先审阅升级计划（或加 --userspace-only 仅升用户态）
apk upgrade
```

新内核作为普通 `linux-image-<release>` APK 与当前内核并存安装，下次重启自动试启动，失败三次回退到上一个内核，`kernelctl list` / `kernelctl check` 查看状态。APK 提交受 `apk-transaction-guard` 保护，异常断电后会在下次启动由 `apk-resume.service` 自动离线续传完成。请勿混用官方 musl 或 Alpine 仓库；升级前请自行备份 home、容器卷和虚拟机磁盘。
详见 [内核升级](docs/kernel-upgrade.md)、[APK 升级预检](docs/apk-upgrade-preflight.md) 与 [APK 事务恢复](docs/apk-transaction-recovery.md)。

## 文档

- **系统与 init**：[原生 systemd](docs/systemd.md)、[systemd 单 init 方案](docs/systemd-only-plan.md)、[纯路由解耦](docs/systemd-router-decoupling-plan.md)、[服务桥接](docs/systemd-service-bridge.md)、[NAS 与辅助服务监管](docs/nas-systemd.md)、[udev 边界](docs/systemd-udev-boundary.md)、[普通用户](docs/multiuser.md)
- **安装与升级**：[USB／光盘安装器](docs/installer-iso.md)、[离线可选组件](docs/installer-components-plan.md)、[内核升级](docs/kernel-upgrade.md)、[LAN APK feeds](docs/lan-apk-feeds.md)、[APK 复建诊断与发布](docs/apk-rebuild-release.md)、[LZ4 SquashFS](docs/squashfs-lz4.md)
- **桌面与多媒体**：[GNOME](docs/gnome-desktop.md)、[桌面设置向导](docs/desktop-setup.md)、[中文输入](docs/desktop-ime.md)、[音频](docs/desktop-audio.md)、[Google Chrome](docs/google-chrome.md)、[Konsole](docs/konsole.md)、[硬件与内核支持](docs/desktop-kernel.md)
- **应用、容器与开发**：[Flatpak](docs/flatpak.md)、[AppImage](docs/appimage.md)、[Podman](docs/podman-rootless.md)、[Distrobox](docs/distrobox.md)、[Libvirt](docs/libvirt.md)、[virt-manager](docs/virt-manager.md)、[原生开发](docs/native-development.md)、[Qt6 开发](docs/qt6-development.md)
- **路由与运维**：[Full cone NAT](docs/fullcone-nat.md)、[DNS 快路径](docs/dnsmasq-nftset.md)、[daed](docs/daed.md)、[irqbalance 网卡 CPU 池](docs/irqbalance-netdev-cpus.md)、[配置历史 uci-history](docs/uci-history.md)、[路由审计 router-audit](docs/router-audit.md)、[重启建议 needrestart](docs/needrestart.md)
- **源码与发布**：[Feeds 仓库清单](configs/github-source-repositories.json)、[GitHub 源码托管](docs/github-source-hosting.md)、[发布就绪规范](docs/publication-readiness.md)

每个功能均有对应的 `docs/*-validation.md` 验证记录。

## 许可

基于 [OpenWrt](https://github.com/openwrt/openwrt)，遵循 GPL-2.0，详见 [COPYING](COPYING)。
各软件包按其自身许可分发。
