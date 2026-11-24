# 当前本地构建的源码保存

`configs/x86-64-systemd-desktop.config` 保存完整的 GNOME 桌面构建配置（x86_64/glibc、
APK、native systemd、Linux 7.3），关闭 Weston、seatd 和旧启动器。在新 checkout 中可以
复制为 `.config`，安装匹配 feeds 后再正常化配置。它不包含测试账号、测试 SSH 密钥或
个人路由器凭据。构建 KDE Plasma 6.8.3 软件包可叠加 `configs/plasma-packages.config`
（`=m`）。需在镜像中预装时使用 `configs/plasma.config`（`=y`）。构建 10 组件离线
安装器 ISO 还需要 `configs/installer-iso.config`，完整合并命令见
[安装器构建步骤](installer-iso.md#build)。

纯路由独立构建配置保存在 `configs/x86-64-systemd-router.config`，可按需通过
`scripts/kconfig.pl +` 叠加模块化片段（如 `configs/gnome-desktop-core.config`、
`configs/plasma.config`、`configs/plasma-packages.config`、`configs/desktop-audio.config`、
`configs/desktop-ime.config`、`configs/flatpak.config`、`configs/appimage.config`、
`configs/firefox-esr.config`、`configs/google-chrome.config`、`configs/qt6-dev.config`、
`configs/podman.config`、`configs/distrobox.config`、`configs/samba4.config`、
`configs/virt-headless.config`、`configs/daed.config`、`configs/uci-history.config`）。
纯路由构建应在独立 checkout 中执行，避免覆盖主工作区
完整桌面 `.config` 与 `bin/systemd` 输出，也避免普通 combined 镜像纳入根目录未跟踪的
个人 `files/`。详见 [纯路由与解耦验证记录](systemd-router-decoupling-validation.md)。

x86/64 正式目标自动启用 glibc、APK 和 systemd。原生 failsafe 使用
`failsafe=true`，整机安装使用安装介质或离线写盘。详见 [systemd 单 init](systemd-only-plan.md)。

## Feed 来源

`feeds.conf.default` 只跟踪上游：OpenWrt 官方 feeds 使用 GitHub 镜像
（`https://github.com/openwrt/<feed>.git`，不使用 git.openwrt.org），
`passwall_packages`/`passwall_luci` 使用 `Openwrt-Passwall` 上游，`taskplan`
使用 `sirpdboy/luci-app-ddns-go`，不指向本地 GitLab。带本地提交的 feed 分支跟踪
`origin/<branch>` 并领先于上游；上游更新后 `./scripts/feeds update` 中的
`git pull --ff-only` 会失败，需要在该 feed 仓库内手动合并。`packages`、`video`、`luci`
和 `taskplan` 的本地提交镜像在 `patches/feeds/`（已编号至 `0052-video-qt6-11-plasma.patch`，
配合各 `configs/*-feeds.json` 清单）；`telephony` 和 Passwall 的本地提交目前只保存在
各自的 feed 仓库中。签名密钥 `private-key.pem`/`public-key.pem` 不在仓库中，需要从现有
构建机单独复制。

`scripts/feeds` 在 feed 地址改变时会删除并重新克隆该 feed；已有工作区更换
`feeds.conf.default` 地址前，应先把新地址写入 `feeds/<name>.tmp/location`，
以保留本地提交、分支和 stash。

## Feed 补丁备份

`packages` 和 `video` feeds 是独立 Git 仓库，主仓库忽略 `feeds/`。
两者的本地修改分别提交；`configs/local-feeds.json` 记录各自的基线和提交。
对应补丁也保存在 `patches/feeds/`，便于随主仓库保存和审阅。

在尚未包含这些修改、工作区干净且基线与清单一致的 feed checkout 中，
以 OpenWrt 根目录作为当前目录执行：

```sh
git -C feeds/packages am "$PWD/patches/feeds/0001-packages-local-integration.patch"
git -C feeds/video am "$PWD/patches/feeds/0001-video-local-integration.patch"
./scripts/feeds install -a
cp configs/x86-64-systemd-desktop.config .config
make defconfig
```

当前工作区已包含这些 feed 提交，不要再次应用补丁。不同上游基线需要
先审阅并解决差异，不能用重置覆盖本地修改。

提交前的配置导出发现现有 Kconfig 依赖循环：`video-support`、
`openwrt-desktop`、`glib2-gir` 与 Mesa 的链路，以及 LuCI weechat 的链路。
`scripts/diffconfig.sh` 未可靠地完成最小化，因此保存完整配置快照。
这些警告仍需单独处理；完整镜像的实际构建和冷启动结果见
[virt-manager-validation.md](virt-manager-validation.md)。

普通用户、SSH、LuCI 的启动脚本和配置保留规则已作为源码跟踪在 `files/`
中。其余被忽略的个人网络、DDNS、VPN/代理配置、备份包、本地工具权限
设置及构建产物仍留在本地。提交内容不预置人类账号、密码或私钥。

### systemd 单 init 的 feed 补丁

`configs/systemd-only-feeds.json` 记录 packages、LuCI 和 taskplan 补丁的起点。
在对应 feed 位于清单中的基线、且尚未包含改动时，使用
`git -C feeds/<feed> apply --check <绝对补丁路径>` 检查，再用
`git -C feeds/<feed> apply <绝对补丁路径>` 重建工作树。随后重新生成 feed 索引和包链接。

## SPICE / VirtIO / OpenGL 增量

`configs/virtio-spice-feeds.json` 单独记录本次图形支持的两个 feed 基线、
提交和 `0002-*-virtio-spice.patch`。它们只包含本次改动，不替代以上历史
清单。在匹配该增量基线且工作区干净的 feed checkout 中应用：

```sh
git -C feeds/packages am "$PWD/patches/feeds/0002-packages-virtio-spice.patch"
git -C feeds/video am "$PWD/patches/feeds/0002-video-virtio-spice.patch"
./scripts/feeds install -a
```

当前 feed 已包含这些提交，不要重复应用。配置片段只覆盖这次图形选项，
保留已有 x86_64/glibc、APK、原生 systemd 及其他配置：

```sh
./scripts/kconfig.pl + .config configs/virtio-spice.config > .config.graphics
mv .config.graphics .config
make defconfig
make -j3 V=s
```

片段用单一 `libmesa-virtualization` 替换其他 Mesa OpenGL provider，启用
SPICE、EGL/GBM、VirGL、GLX 和 Vulkan ICDs。新建客体仍默认关闭 3D；手动启用需要
渲染节点权限。操作见 [virt-manager.md](virt-manager.md)，当前虚拟化与 SPICE 验证见
[libvirt-uefi-passthrough-validation.md](libvirt-uefi-passthrough-validation.md) 和
[spice-egl-build-validation.md](spice-egl-build-validation.md)。

## Fastfetch 和 Argon 的 custom feed 更新

这两个包位于 `package/custom/fastfetch` 和
`package/custom/luci-theme-argon`，由 `configs/custom-package-updates.json`
登记。`./scripts/feeds update custom`（或 `update -a`）自动检查上游；
`./scripts/feeds update -i custom` 只重建索引。

Fastfetch 按 `fastfetch-cli/fastfetch` 的最新稳定 release 更新版本与
SHA256，允许跨次版本升级，保留本地 CMake 裁剪选项。
`PKG_VERSION` 使用上游版本（当前为 `2.71.0`），源码目录和下载地址
也使用该版本。安装包版本保留固定兼容前缀 `2026.06.28.`（例如
`2026.06.28.2.71.0-r1`），高于旧快照 `2026.06.28~0e90f3a7-r3`，
可以正常升级，无需显式降级。此前缀保持不变，后续稳定版继续按上游
版本递增。

Argon 保留独立 Git 仓库，追踪 `jerrykuku/luci-theme-argon` 的 `master`
（包括稳定版发布后的修复）。新 checkout 中 `./scripts/feeds update`
会自动执行 `git submodule update --init` 从本地 GitLab 初始化已保存的历史，
并切换到 `master` 分支。更新器合并上游并保留本地提交；合并前先检测
冲突，有已跟踪文件改动、隐藏索引标记或未完成 Git 操作时停止，不覆盖
未跟踪文件。更新前的 HEAD 保存在嵌套仓库的
`refs/custom-package-updates/`，报告位于 `logs/custom-package-updates/`。
同版本源码更新会递增 `PKG_RELEASE`，该工作区改动应在下次更新前于
Argon 仓库单独审阅并提交。版本或内容冲突需要人工解决。

仅检查这两个包，不更新其他 custom 包：

```sh
python3 scripts/update-custom-packages.py --check --package fastfetch --package luci-theme-argon
python3 scripts/update-custom-packages.py --update --package fastfetch --package luci-theme-argon
./scripts/feeds update -i custom
./scripts/feeds install -p custom fastfetch luci-theme-argon
make package/custom/fastfetch/compile V=s
make package/custom/luci-theme-argon/compile V=s
```

更新新迁移但尚未提交的 Fastfetch 配方时，现有的脏配方保护仍然生效；
先审阅并提交主仓库中的迁移，再让后续 feed 更新修改该配方。
