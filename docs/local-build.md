# 当前本地构建的源码保存

本源码集合包含 virt-manager、自定义包、开发工具、GNOME 桌面、libvirt、
普通用户/SSH 支持以及配套目标配置。主树与各 feed 分别维护提交历史。

`configs/x86-64-systemd-desktop.config` 保存完整构建配置，现已合并
`configs/gnome-desktop.config`，使用 GNOME 与原生 systemd/udev。
当前桌面的验收范围见 GNOME 验证与物理部署记录。
在新 checkout 中可以复制为 `.config`，安装匹配 feeds 后再正常化配置。
它不包含测试账号、测试 SSH 密钥或个人路由器凭据。

## Feed 来源

`feeds.conf.default` 指向 `hnt510-great` 账号下的 8 个私有 GitHub feed 仓库。
它们保存现有本地提交；`custom` 仍直接链接主树的 `package/custom`。
主树、主题、各 feed 的地址和分支见
[`configs/github-source-repositories.json`](../configs/github-source-repositories.json)。
停用的 `argon_config` 保存于主题仓库的 `retired-argon-config` 独立归档分支，
不加入活动 feeds。清单中的 `local_branch` 仅描述迁移工作区的原分支名；
新 clone 使用 `branch` 指定的 GitHub 分支。

新机器先登录有权访问这些私有仓库的 GitHub 账号，再执行：

```sh
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
git clone https://github.com/hnt510-great/openwrt.git
cd openwrt
./scripts/feeds update -a
./scripts/feeds install -a
cp configs/x86-64-systemd-desktop.config .config
make defconfig
```

只在新 checkout 中复制配置；保留已有工作区的 `.config`。`update -a` 除拉取
私有 feed 分支外，还会检查并更新注册的 custom 配方，可能产生工作区修改。
它不会自动将 OpenWrt 官方或 Passwall 上游合并进你的私有 feed。
签名密钥 `private-key.pem`/`public-key.pem` 不在仓库中，需单独管理。

维护者在各仓库保留 `origin` 指向私有 GitHub，`upstream` 指向清单中的原始
项目。新 clone 如需同步上游，先按清单添加 `upstream`，然后审阅、合并、测试并
推送，例如：

```sh
git -C feeds/packages remote add upstream https://github.com/openwrt/packages.git
git -C feeds/packages fetch upstream
git -C feeds/packages merge upstream/master
# 审阅并验证修改后
git -C feeds/packages push origin master
```

其他机器再执行 `./scripts/feeds update -a`，即可快进到已推送的私有 feed。
`patches/feeds/` 和旧功能清单保留为历史备份；从这些私有仓库获取源码时，
不要重复应用已有补丁。旧工作区的 GitLab 远程保留在其他 remote 名称下。

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
SPICE、EGL/GBM、VirGL 并保留 VNC。新建客体仍默认关闭 3D；手动启用需要
渲染节点权限和 GL 桌面。操作见 [virt-manager.md](virt-manager.md)，完整镜像
校验和、嵌套 GPU 测试和实体 Intel 测试边界见
[virtio-spice-validation.md](virtio-spice-validation.md)。现有 weechat Kconfig
循环属于此前问题；本次已修复图形能力包的依赖选择循环。

## Fastfetch 和 Argon 的 custom feed 更新

这两个包位于 `package/custom/fastfetch` 和
`package/custom/luci-theme-argon`，由 `configs/custom-package-updates.json`
登记。`./scripts/feeds update custom`（或 `update -a`）自动检查上游；
`./scripts/feeds update -i custom` 只重建索引。

Fastfetch 按 `fastfetch-cli/fastfetch` 的最新稳定 release 更新版本与
SHA256，允许跨次版本升级，保留本地 CMake 裁剪选项。
`PKG_VERSION` 使用上游版本（当前为 `2.70.0`），源码目录和下载地址
也使用该版本。安装包版本保留固定兼容前缀 `2026.06.28.`，生成
`2026.06.28.2.70.0-r1`，高于旧快照 `2026.06.28~0e90f3a7-r3`，
可以正常升级，无需显式降级。此前缀保持不变，后续稳定版仍按上游
版本递增，例如 `2026.06.28.2.71.0-r1`。

Argon 保留独立 Git 仓库，追踪 `jerrykuku/luci-theme-argon` 的 `master`
（包括稳定版发布后的修复）。新 checkout 中 `./scripts/feeds update`
会自动执行 `git submodule update --init` 从私有 GitHub 主题仓库初始化已保存的历史，
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
