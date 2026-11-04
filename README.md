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
