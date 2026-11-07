# OpenWrt Systemd Host

**简体中文** | [English](README.en.md)

<img width="1931" height="1085" alt="Screenshot From 2026-11-05 22-06-51" src="https://github.com/user-attachments/assets/5694540a-657b-4a43-9fa8-368ae20a1a75" />

面向 x86_64 的 OpenWrt 分支：一台机器同时做路由器、GNOME 桌面、容器与虚拟机主机。
保留 UCI、LuCI 和 procd 服务接口，底层改为 glibc、签名 APK 和原生 systemd，
内核跟踪 Linux 主线。

## 主要特性

- **系统基础**：glibc、APK 签名包、合并 `/usr`、systemd 作为 PID 1；GRUB 保留 procd 恢复项
- **桌面**：GNOME 51（本地 VT7），RDP 与 Sunshine/Moonlight 共享同一会话；Fcitx5 中文输入、PipeWire 音频、Firefox ESR
- **应用与容器**：Flatpak、AppImage、Rootless Podman/Quadlet、Distrobox、原生开发工具链
- **虚拟化**：QEMU/KVM、libvirt、virt-manager、SPICE/VirGL
- **路由**：Full cone NAT、dnsmasq nftset netlink 快路径；默认 Passwall，可选 daed（eBPF，默认停用）
- **升级**：内核按批次打包并带 GRUB 试启动与回退；发布前对真实路由器做 APK 升级预检

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

新 checkout 使用保存的完整桌面配置构建：

```sh
cp configs/x86-64-systemd-desktop.config .config
make defconfig
make download
python3 scripts/build-and-publish.py build-only -j12 V=s
```

`build-only` 会预留内核批次号，但不发布、不部署。已有工作区请保留自己的 `.config`，
按需用 `scripts/kconfig.pl` 合并 `configs/<功能>.config` 片段。单包构建：

```sh
make package/custom/openwrt-desktop/compile V=s
```

完整桌面配置已启用安装 ISO，产物位于 `bin/systemd/`。已有配置如需启用安装器，
在构建前合并配置片段：

```sh
./scripts/kconfig.pl + .config configs/installer-iso.config > .config.new
mv .config.new .config
make defconfig
```

更多说明见 [本地构建](docs/local-build.md)。

## 安装

### 使用安装 ISO

安装器支持 **UEFI 和传统 BIOS** 启动，目标盘建议 16 GB 以上。
准备一个安装 U 盘和一块独立目标盘，将 ISO 原始写入整个 U 盘。
可用 Etcher、Rufus 的 **DD 模式**，或下面的命令；先确认设备名，
将 `/dev/REPLACE_USB` 换成实际 U 盘设备，写入会清空该 U 盘：

```sh
sudo dd if=bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-installer.iso of=/dev/REPLACE_USB bs=4M conv=fsync status=progress
sync
```

1. 从 U 盘启动，选择 **Install OpenWrt**；串口终端选择 **Install OpenWrt (serial console)**。
2. 在英文文本向导中选择目标盘与分区方案。引导分区使用 FAT32，系统使用只读 squashfs，
   可写分区默认 ext4，也可选择 btrfs 或 xfs。
3. 根据 MAC 地址、驱动和链路状态选择 WAN/LAN 网口，设置网络、防火墙和 root 密码。
   默认 LAN 为 `192.168.1.1/24`；WAN 支持 DHCP、PPPoE、静态地址或不配置。
4. 可选创建普通用户并启用 GNOME 自动启动。确认摘要后执行安装：
   **所选目标盘会重新分区，原有数据全部清除，不保留原分区或双系统。**
5. 安装完成后移除 U 盘并重启，从目标盘启动；UEFI 安装无需修改 NVRAM 启动项。

虚拟机可将同一个 ISO 挂载为 **SATA CD-ROM**，设置光驱优先启动，并添加独立可写磁盘；
virt-manager 中已验证的安装器显示型号为 **Standard VGA**。
安装后弹出 ISO。Rufus ISO 模式和 Ventoy 暂不支持。
详细操作、分区说明和故障日志见 [USB／光盘安装器](docs/installer-iso.md)。

### 直接写入磁盘镜像

也可在其他系统或 Live 环境中，将 `combined-efi` 镜像直接写入目标盘，再以 **UEFI** 启动。
将 `/dev/REPLACE_DISK` 换成实际目标磁盘，写入会清空目标盘：

```sh
gunzip -c bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz | sudo dd of=/dev/REPLACE_DISK bs=4M conv=fsync status=progress
sync
```

直接写盘使用镜像预设的分区和配置；安装 ISO 则通过向导生成配置，并排除未跟踪的个人 overlay。

**已运行本固件**：systemd 模式下拒绝 `sysupgrade` 刷写。重启进入 GRUB 的
`procd recovery` 项，再执行 `sysupgrade <镜像>`。日常升级通常无需重刷，见下文“升级”。

## 首次使用

1. 从 GRUB 默认项启动，确认 `cat /proc/1/comm` 输出 `systemd`。
   通过安装器安装时，使用向导设置的 root 密码；直接写盘后应先在控制台设置 root 密码。
2. 浏览器打开 `http://LAN-IP/` 登录 LuCI。安装器默认 LAN 地址为 `192.168.1.1`，
   如在向导中修改过则使用修改后的地址；按需调整 WAN/LAN、DNS 和时区。
3. 首次进入 LuCI 会自动打开**桌面设置向导**（之后可在 **系统 → 桌面设置向导** 打开），
   创建或选择普通用户，并勾选 GNOME/RDP、Moonlight、容器、Flatpak、虚拟机等功能。
   安装器已创建用户并启用 GNOME 时，可直接使用该用户，按需补充远程桌面等设置。
   详见 [桌面设置向导](docs/desktop-setup.md)。

也可以在 root shell 中手动完成（`alice` 换成自己的用户名）：

```sh
useradd -m -U alice && passwd alice && usermod -aG sudo alice
desktop-setup alice                    # 启动 VT7 上的 GNOME
desktop-rdp-setup alice                # 设置 RDP 密码，输出证书指纹
sunshine-setup alice --capture=portal  # 可选：Moonlight 串流
podman-rootless-setup alice            # 可选：rootless 容器
flatpak-user-setup alice               # 可选：用户级 Flatpak
virt-manager-setup alice               # 可选：本机虚拟机管理
/etc/init.d/desktop restart
```

连接方式：

| 功能 | 使用 |
| --- | --- |
| 本地桌面 | 接显示器与键鼠，**Ctrl+Alt+F7** |
| RDP | `LAN-IP:3389`，用户名 `alice`，密码为 RDP 密码 |
| Moonlight | 先在 `https://LAN-IP:47990` 设置 Sunshine 账号，再在 Moonlight 中 PIN 配对 |
| 容器 / 虚拟机 | `podman`、LuCI **服务 → Rootless Podman**；virt-manager 连接 `qemu:///system` |
| 代理 | LuCI **服务 → Passwall** 填写节点；切换 daed 见 [daed](docs/daed.md) |
| Full cone NAT | LuCI **网络 → 防火墙 → 常规设置** 勾选 |

## 升级

设备从构建机发布的 LAN APK 源安装和升级软件。构建机按
[LAN APK feeds](docs/lan-apk-feeds.md) 发布后，在设备的 `/etc/lan-apk-feeds.conf`
中填写真实 `base_url`，然后：

```sh
lan-apk-feeds-sync
apk update
apk upgrade --simulate   # 先审阅计划
apk upgrade
```

新内核作为普通 APK 安装，下次启动自动试运行，失败三次回退到上一个内核，`kernelctl check`
查看状态。不要混用官方 musl 或 Alpine 仓库。升级前请自行备份 home、容器卷和虚拟机磁盘。
详见 [内核升级](docs/kernel-upgrade.md) 与 [APK 升级预检](docs/apk-upgrade-preflight.md)。

## 文档

- 系统：[原生 systemd](docs/systemd.md)、[普通用户](docs/multiuser.md)
- 桌面：[GNOME](docs/gnome-desktop.md)、[中文输入](docs/desktop-ime.md)、[音频](docs/desktop-audio.md)、[硬件支持](docs/desktop-kernel.md)
- 应用：[Flatpak](docs/flatpak.md)、[AppImage](docs/appimage.md)、[Podman](docs/podman-rootless.md)、[Distrobox](docs/distrobox.md)、[Libvirt](docs/libvirt.md)、[原生开发](docs/native-development.md)
- 网络：[Full cone NAT](docs/fullcone-nat.md)、[DNS 快路径](docs/dnsmasq-nftset.md)、[daed](docs/daed.md)
- 源码：[Feeds 仓库清单](configs/github-source-repositories.json)、[GitHub 源码托管](docs/github-source-hosting.md)

每个功能都有对应的 `docs/*-validation.md` 验证记录。

## 许可

基于 [OpenWrt](https://github.com/openwrt/openwrt)，遵循 GPL-2.0，详见 [COPYING](COPYING)。
各软件包按其自身许可分发。
