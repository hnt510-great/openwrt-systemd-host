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
