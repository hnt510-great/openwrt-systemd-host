# OpenWrt：路由器与 GNOME 桌面

**简体中文** | [English](README.en.md)

面向 x86_64 的 OpenWrt 定制主树，将路由、普通用户 GNOME 桌面、容器与
本机虚拟化整合在同一套系统中。项目保留 UCI、LuCI 和 procd 服务接口，
使用 glibc、APK 和原生 systemd，并跟踪 Linux 7.3 主线内核系列。

## 项目特点

| 领域 | 实现 |
| --- | --- |
| 系统基础 | x86_64、glibc、签名 APK、合并 `/usr` 布局、原生 systemd；procd 提供 OpenWrt 服务与恢复接口 |
| 桌面 | GNOME 51 普通用户 Wayland 会话，包含 Files、Terminal、Tweaks、Firefox ESR 和中文输入支持 |
| 远程访问 | GNOME Remote Desktop 的 LAN RDP 与 Sunshine/Moonlight 共享本地同一个桌面会话 |
| 音频与输入 | PipeWire/WirePlumber、PulseAudio 兼容层、Fcitx5 与 GNOME Kimpanel |
| 应用与开发 | 用户级 Flatpak、AppImage、原生开发工具、Rust 构建支持 |
| 容器与虚拟化 | Rootless Podman、systemd/Quadlet、QEMU/KVM、libvirt、virt-manager 与 SPICE/VirGL |
| 路由增强 | Full cone NAT、dnsmasq nftset netlink 快路径；Passwall 为默认代理方案，daed 为默认停用的替代方案 |
| 升级 | ELF/ucode ABI 检查、不可变 APK 身份、内核生成批次与试启动、基于路由器升级预检的发布流程 |

这是配套维护的主树与 feeds 组合。具体选项见
[`configs/x86-64-systemd-desktop.config`](configs/x86-64-systemd-desktop.config)，
架构与运行方式见 [原生 systemd](docs/systemd.md) 和 [GNOME 桌面](docs/gnome-desktop.md)。

## 新刷机后：启用与使用

完整桌面配置现已选择 `luci-app-desktop-setup`。首次登录 LuCI 概览时，
有配置权限的管理员会自动进入**桌面设置向导**，按“账号 → 功能 → 确认 → 结果”
创建或选择普通用户，再登记 GNOME/RDP、Moonlight、容器、Flatpak 与虚拟机权限。
完成后或选择“稍后设置”后不再自动进入，仍可通过
**系统 → 桌面设置向导** 随时单独打开。详见 [向导说明](docs/desktop-setup.md)。
下面保留手工配置流程，供不使用向导或排查问题时参考。

以下适用于按本项目完整桌面配置构建的镜像。`alice` 是示例普通用户名，
请统一替换成自己的用户名；`LAN-IP` 指设备实际 LAN 地址。标明 **root** 的
命令在设备的 root 控制台或 SSH 中执行，标明 **普通用户** 的命令在该用户
重新登录后的 SSH 或 GNOME 终端中执行。裁剪镜像缺少的包需通过匹配的 APK 源
补齐，不能仅靠下面的开关启用。

### 1. 确认启动模式、网络和管理员密码

从 GRUB 默认的原生 systemd 项启动；`procd recovery` 用于恢复和刷写，
不能用于运行 GNOME。首次通过本地控制台进入后，以 **root** 检查：

```sh
cat /proc/1/comm
ip -4 addr
passwd
```

PID 1 应为 `systemd`。记录实际 LAN 地址，在同一 LAN 的电脑打开
`http://LAN-IP/` 或已配置的 `https://LAN-IP/` 登录 LuCI。先在 LuCI 完成
LAN/WAN 网口、DHCP/PPPoE、DNS 和时区设置，确认设备能解析域名并访问外网。
网口分配、运营商账号和无线参数按自己的硬件与网络填写。

准备存放虚拟机、容器或大量应用时，先规划并挂载持久数据盘，再初始化对应
存储。`/tmp` 是临时空间，完整配置备份也不等于虚拟机磁盘或容器数据备份。

### 2. 配置本项目的 APK 软件源

已装入镜像的功能可以直接配置使用。需要安装或更新软件时，先由构建机按
[LAN APK feeds](docs/lan-apk-feeds.md) 发布匹配的已签名包，再在设备以
**root** 编辑 `/etc/lan-apk-feeds.conf`，把 `base_url` 换成自己的真实源地址。
仓库中的 `apk.example.invalid` 是示例，不能直接下载软件。

确认包签名信任与该镜像匹配后执行：

```sh
lan-apk-feeds-sync
apk update
```

GitHub 上的 feeds 是构建配方仓库，不是可直接填入 APK 配置的软件包源。
本镜像使用 glibc/native-systemd 配套包，不能混用官方 musl 或 Alpine 仓库。

### 3. 创建普通用户，启动本地 GNOME 与 RDP

在设备以 **root** 执行。第一次创建账号时运行前两行；已有账号则跳过：

```sh
useradd -m -U alice
passwd alice
usermod -aG sudo alice
desktop-setup alice
desktop-rdp-setup alice
```

`sudo` 组授予该用户管理员权限。`desktop-setup` 配置并启动 VT7 上的 GNOME，
同时准备无人值守的 keyring 解锁；已有登录 keyring 会询问其原密码。
`desktop-rdp-setup` 交互设置独立的 RDP 密码，并输出 TLS 证书指纹。

接上显示器、键盘和鼠标即可使用本地桌面；需要切换虚拟终端时使用
**Ctrl+Alt+F7**。远程电脑用 RDP 客户端连接 **`LAN-IP:3389`**，用户名为
`alice`，密码为刚设置的 RDP 密码，并核对证书指纹。RDP 与本地显示器共享同一
GNOME 会话。Files、Terminal、Tweaks 和 Firefox 可从应用概览启动；中文输入
使用 **Ctrl+Space** 切换，已有 Fcitx 配置保留其原快捷键。

### 4. 启用 Moonlight、容器、Flatpak 与虚拟机权限

需要这些功能时，在设备以 **root** 为同一用户登记：

```sh
sunshine-setup alice --capture=portal
podman-rootless-setup alice
flatpak-user-setup alice
virt-manager-setup alice
uci add_list 'luci_podman.main.users=alice'
uci commit luci_podman
/etc/init.d/desktop restart
```

这些操作分别启用 Sunshine/音频及虚拟输入、rootless 容器的 subordinate IDs
和 linger、用户级 Flatpak 存储、完整本机虚拟机管理权限，以及 LuCI Podman
账号白名单。`libvirt-admin` 是接近 root 的可信管理员权限。白名单也可在
**LuCI → 服务 → Rootless Podman → 配置** 中选择账号并保存；同一用户只添加一次。
最后的桌面重启用于刷新组成员与会话，关闭的是桌面应用。随后重新登录普通用户
SSH，以取得更新后的组权限。

如果只使用 RDP、不启用 Sunshine，仍需由 **root** 执行
`desktop-audio-setup alice`，以开启桌面播放与麦克风权限。

| 功能 | 首次使用方法 |
| --- | --- |
| Moonlight 串流 | 打开 **`https://LAN-IP:47990`** 设置 Sunshine Web 管理账号；Moonlight 添加 `LAN-IP` 并完成 PIN 配对。Portal 首次捕获可能需要在 GNOME 中选择共享屏幕。需 KMS 时用 `sunshine-setup alice --enable-kms` 替代 portal 登记，再重启桌面 |
| 桌面音频 | 在 GNOME 声音设置选择实际输出/输入；RDP 客户端开启播放/麦克风重定向，Moonlight 使用 Sunshine 音频。普通用户可用 `wpctl status` 检查设备 |
| Rootless Podman | 普通用户执行 `podman info`；LuCI 的 **服务 → Rootless Podman** 选择已授权的 `alice`，先拉取镜像再创建、启动容器。Compose/Quadlet 见 [Podman systemd 指南](docs/podman-systemd.md) |
| 虚拟机 | 在固件/BIOS 开启 CPU 虚拟化后，普通用户启动 Virtual Machine Manager，连接 `qemu:///system`，选择 ISO、存储与已有 `br-lan` 桥创建客体。**服务 → QEMU 虚拟机** 管理已定义客体，不负责创建；3D 需单独验证，设备直通不属于当前 libvirt 管理范围 |
| GNOME 设置 | 显示、键鼠、声音、背景等在 GNOME Settings/Tweaks 调整；路由网络在 LuCI 配置。驱动与固件支持不等于已经配置 Wi-Fi、蓝牙或外设，见 [硬件支持](docs/desktop-kernel.md) |
| Distrobox 与开发 | 普通用户按 [Distrobox](docs/distrobox.md) 创建开发容器；已包含的 GCC、CMake、Python 和开发库无需启用服务，见 [原生开发](docs/native-development.md) |

在 **普通用户的 GNOME 终端** 添加 Flathub 并安装第一个应用：

```sh
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub org.gnome.Calculator
flatpak run --user org.gnome.Calculator
```

AppImage 无需开启后台服务。普通用户下载并核对应用文件后执行：

```sh
chmod +x ~/Applications/Application-x86_64.AppImage
~/Applications/Application-x86_64.AppImage
```

把示例路径换成实际文件；应用库兼容性和存储要求见 [AppImage](docs/appimage.md)。

### 5. 配置路由增强、共享和 DDNS

这些功能需要自己的节点、域名或共享目录，不会由用户登记脚本自动填入：

| 功能 | 启用位置或操作 |
| --- | --- |
| Passwall | 在 **LuCI → 服务 → Passwall** 填写自己的节点/订阅、DNS 和分流策略，保存后启用。它是本项目默认选择的代理方案 |
| Full cone NAT | 默认关闭。在 **网络 → 防火墙 → 常规设置** 勾选 Full cone NAT 并保存应用。它作用于直接 NAT 转发，不能代表代理出口行为 |
| DNS nftset 快路径 | 随带补丁的 dnsmasq/nftables 使用，无独立后台服务开关；仍需由 Passwall 或自己的 DNS 规则配置 nftset，见 [DNS 快路径](docs/dnsmasq-nftset.md) |
| Samba | 在 **服务 → 网络共享** 配置实际目录、允许用户及读写权限；默认没有共享目录。需要密码访问时，由 root 执行 `smbpasswd -a alice`，Samba 密码独立于系统密码 |
| DDNS-Go | 在 **服务 → DDNS-GO** 配置和启用服务，按页面填写服务商授权、域名及地址来源，并检查更新日志 |
| 日志与重启提示 | **状态 → 系统日志 → Systemd Journal** 查看服务日志；**状态 → Restart Needed** 扫描升级后需重启的进程。扫描不会自动重启服务 |

**daed 是 Passwall 的二选一替代方案，默认停用。** 只有准备切换时，才以
**root** 执行下面的命令；不要与启用 Passwall 的步骤一起执行：

```sh
uci set 'passwall.@global[0].enabled=0'
uci commit passwall
/etc/init.d/passwall stop
uci set daed.config.enabled=1
uci commit daed
/etc/init.d/daed enable
/etc/init.d/daed start
```

随后从 LAN 打开 **`http://LAN-IP:2023/`**，立即创建管理员账号，再填写节点、
DNS 与路由规则，确认 `br-lan` 等实际接口。内核要求、互斥机制和切换说明见
[daed](docs/daed.md)。

### 6. 检查与日常升级

设备上以 **root** 检查系统、桌面和内核：

```sh
systemctl --failed
/etc/init.d/desktop status
kernelctl check
needrestart
```

在重新登录的 **普通用户** 会话中检查：

```sh
systemctl --user status podman.socket
podman info
virsh -c qemu:///system list --all
```

按需验证 RDP/Moonlight 的输入与音频、中文输入、容器联网、虚拟机启动、共享
和 DDNS，不能用“服务已启动”代替实际功能测试。更多故障诊断见下方各功能文档。

软件源可用后，`apk update` 只刷新索引；安装先用 `apk add --simulate 包名`
审阅计划，再执行实际安装。完整升级、内核试启动与回退按
[内核升级](docs/kernel-upgrade.md) 和 [APK 预检](docs/apk-upgrade-preflight.md)
操作。升级前另行备份用户 home、keyring/RDP/Sunshine 配置、Flatpak 数据、
容器卷、虚拟机定义和磁盘。主机构建机的定时维护仍保持停用，不属于设备首次启用步骤。

## 获取源码

主树、8 个活动 feeds 和 Argon 主题共使用 10 个私有 GitHub 仓库。
构建账号需要对这些仓库具有读取权限。先在构建机完成认证：

```sh
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
git clone https://github.com/hnt510-great/openwrt.git
cd openwrt
./scripts/feeds update -a
./scripts/feeds install -a
```

`custom` feed 直接链接主树的 `package/custom`；更新器会初始化 Argon 主题
子模块，并检查注册的 custom 包上游版本，因此 `update -a` 可能修改配方。
已有工作区只需重建索引时，使用 `./scripts/feeds update -i -a`。

## 配置与构建

使用具备 OpenWrt 构建依赖的 Linux 主机。项目保留完整配置和按功能拆分的片段。
仅在新 checkout 中恢复保存的完整配置：

```sh
cp configs/x86-64-systemd-desktop.config .config
make defconfig
make download
python3 scripts/build-and-publish.py build-only -j12 V=s
```

已有工作区应保留 `.config`，需要时用 `scripts/kconfig.pl` 合并功能片段。
`build-only` 为完整构建保留内核生成批次，且不发布 APK、不部署设备。
原生 systemd 的固件和包输出位于 `bin/systemd/`。

单包构建示例：

```sh
make package/custom/openwrt-desktop/compile V=s
make package/feeds/packages/qemu/compile V=s
```

完整新镜像必须搭配相同 ABI 的模块和开发头文件。构建流程、配置恢复与历史
feed 补丁说明见 [本地构建](docs/local-build.md)。

## Feeds 与维护

| Feed | 私有仓库 | 用途 |
| --- | --- | --- |
| `packages` | [openwrt-packages](https://github.com/hnt510-great/openwrt-packages) | 系统库、应用、容器和虚拟化依赖 |
| `luci` | [openwrt-luci](https://github.com/hnt510-great/openwrt-luci) | Web 管理界面及本地集成 |
| `video` | [openwrt-video](https://github.com/hnt510-great/openwrt-video) | 图形库、Mesa 和显示组件 |
| `routing` | [openwrt-routing](https://github.com/hnt510-great/openwrt-routing) | 可选路由与组网软件 |
| `telephony` | [openwrt-telephony](https://github.com/hnt510-great/openwrt-telephony) | 语音通信及相关依赖 |
| `passwall_packages` | [openwrt-passwall-packages](https://github.com/hnt510-great/openwrt-passwall-packages) | 代理核心、DNS 工具和规则数据 |
| `passwall_luci` | [openwrt-passwall-luci](https://github.com/hnt510-great/openwrt-passwall-luci) | Passwall 页面、服务脚本和翻译 |
| `taskplan` | [openwrt-taskplan](https://github.com/hnt510-great/openwrt-taskplan) | DDNS-Go 服务和 LuCI 界面 |

各 feed 独立提交。`scripts/feeds update` 拉取私有分支；维护者将原始上游
合并、验证并推送后，其他机器才能取得相应更新。仓库地址、分支和原始上游见
[源码仓库清单](configs/github-source-repositories.json) 与
[私有 GitHub 托管说明](docs/github-source-hosting.md)。

## 设备配置与文档

固件不预置个人账号、密码、SSH 密钥或代理配置。创建普通用户后，在设备上
使用 `desktop-setup USER`、`desktop-rdp-setup USER` 等工具进行显式配置。
桌面、代理和虚拟机的使用说明见：

- [普通用户与账号](docs/multiuser.md)、[GNOME 会话与远程桌面](docs/gnome-desktop.md)
- [中文输入](docs/desktop-ime.md)、[桌面音频](docs/desktop-audio.md)、[Firefox](docs/firefox.md)
- [Flatpak](docs/flatpak.md)、[AppImage](docs/appimage.md)、[原生开发](docs/native-development.md)
- [Rootless Podman](docs/podman-rootless.md)、[Libvirt](docs/libvirt.md)、[虚拟机管理](docs/virt-manager.md)
- [Full cone NAT](docs/fullcone-nat.md)、[DNS 快路径](docs/dnsmasq-nftset.md)、[daed](docs/daed.md)
- [内核升级](docs/kernel-upgrade.md)、[APK 升级预检](docs/apk-upgrade-preflight.md)、[发布准备](docs/publication-readiness.md)

`docs/*-validation.md` 区分源码检查、VM 和物理设备结果；历史记录不代表
当前每次构建均已验收。当前桌面证据见 [GNOME 验证](docs/gnome-desktop-validation.md)
及其链接的物理部署记录。

APK 发布与设备部署是独立操作；生产发布要求可达路由器及通过升级预检。
主机定时维护保持停用。个人 overlay、凭据、签名密钥和构建产物不纳入源码仓库。

## 许可与来源

本项目基于 [OpenWrt](https://github.com/openwrt/openwrt)，保留其 GPL-2.0
许可和上游版权。各软件包按各自配方和源码中的许可声明分发；详见 [COPYING](COPYING)。
