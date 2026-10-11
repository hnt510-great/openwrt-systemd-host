# 当前本地构建的源码保存

本次提交同时包含 virt-manager 移植和此前未提交的自定义包、开发工具、
Weston 桌面、libvirt、普通用户/SSH 支持以及目标配置修改。

`configs/x86-64-systemd-desktop.config` 保存本次已冷启动验收的完整构建配置。
在新 checkout 中可以复制为 `.config`，安装匹配 feeds 后再正常化配置。
它不包含测试账号、测试 SSH 密钥或个人路由器凭据。

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
