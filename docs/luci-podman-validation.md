# LuCI Rootless Podman 验证，2026-10-14

使用当前 x86_64/glibc native-systemd 构建配置编译应用和中文语言包。
将最终签名 APK 安装到独立 QEMU overlay，基于之前的 Podman 5.8.4
验证 VM；没有修改 backing image，没有连接或部署到物理路由器。
本次验证的是安装包，不是包含新应用的重新构建固件镜像。

## 构建与回归

以下命令通过：

```sh
make package/custom/luci-app-podman/compile V=s \
  CONFIG_PACKAGE_luci-app-podman=m CONFIG_PACKAGE_luci-i18n-podman-zh-cn=m
python3 scripts/tests/test-luci-podman.py
node scripts/tests/test-luci-podman-view.js
cc -Wall -Wextra -Werror -o /tmp/podman-luci-exec \
  package/custom/luci-app-podman/src/podman-luci-exec.c
sh -n package/custom/luci-app-podman/root/usr/libexec/podman-luci-job
git diff --check
```

后端 7 项回归覆盖账号与 subordinate-ID 筛选、白名单拒绝、固定只读命令、
错误返回、非法 ID/动作/参数、后台任务及参数引号、Pod/网络/卷/镜像命令，
以及伪造任务目录 symlink 的拒绝。
前端检查覆盖只读按钮、恶意名称的文本呈现、账号选择、账号切换后的旧响应
丢弃，以及确认操作时账号已改变的拒绝。

构建日志仍有配置未同步提示，以及已有内核配置缺少若干模块的空包提示；
应用包编译退出码为 0。使用命令行包选择，没有执行 defconfig 或改写已有配置。

## QEMU 实际操作

- `podman-luci-exec desktop-user info` 确认 rootless=true、serviceIsRemote=false，
  UID 映射的 host UID 为 32769，存储位于该用户的 HOME，使用 systemd cgroups。
- root 账号被拒绝；普通用户直接调用执行助手也被拒绝。助手无 setuid 位。
- 容器创建保留含引号、空格和 `$(id)` 的环境变量值，按参数传入；创建带端口、
  命名卷及自定义网络的 Alpine 容器通过。
- 容器 start/stop/restart/pause/unpause、inspect、logs 和 rm 通过。
  rootful `podman ps --all` 看不到该测试容器。
- Pod 默认分组模式在加入容器后 start/restart/stop/rm 通过。
  显式使用 Alpine infra 镜像和 `/bin/sleep 600` 的共享命名空间 Pod
  start/stop/rm 通过。
- 镜像的真实后台 pull 和 rm 通过；网络与卷的 create/inspect/list/rm 路径
  中，create/list/rm 已实际执行，详情使用通用 inspect 后端。
- 第二个普通用户 `podmanluciqa` 的 rootless info 和空容器列表通过，存储位于
  `/home/podmanluciqa/`，与 desktop-user 相互独立。
- 实际只读 rpcd 登录允许 list/detail/job，拒绝 action；Chrome 验证只读页面
  仅显示详情和日志，没有创建、启停、删除按钮。
- Chrome 检查了概览、容器列表、真实日志对话框、账号白名单配置及镜像列表。
  中文字段和镜像大小正常呈现。
- 最终 APK 同版本重装前后，`/etc/config/luci_podman` 校验值相同，保留两个
  已配置账号。安装后的 RPC 脚本、任务脚本、打包剥离后的 C 助手及前端资源
  与最终 APK 打包目录的 SHA256 一致。

测试中发现内置 Pod infra 根文件系统在当前内核上启动失败，报 overlay
`invalid argument`。应用提供无 infra 的默认分组模式及显式 infra 镜像选项，
两种模式均完成运行验证；没有改动用户的 containers/storage 配置。

多次同版本重装时，已有 Argon 主题会缓存旧前端。仅在测试 VM 临时增加静态
资源 URL 的验证版本标记，以检查最终页面；之后恢复原主题模板。仓库中的
主题及其他现有改动未被修改。只读测试登录包含 LuCI 基础与标准 session
探测 ACL，避免把缺失 session access 权限误报为会话过期。

测试资源已通过应用后端移除，测试 VM 已关闭。物理设备、procd 运行路线及
新应用随完整固件启动未在本次验证。

## 最终 APK

| 包 | SHA256 |
| --- | --- |
| `luci-app-podman-1.0.0-r1.apk` | `291f1134de0c5a4597bc0c8e554a7f00a704df0ae52009a4f6bf663016365590` |
| `luci-i18n-podman-zh-cn-0.apk` | `c7af45ec828fd8442af184404d13ea2003ef286cc5491ce599914bbba0bbd32f` |

包位于 `bin/systemd/packages/x86_64/base/`。
私有安装日志、完整 RPC 操作记录、校验值及隔离测试磁盘位于
`/srv/openwrt-validation/luci-podman-validation-20261014/`。

## 后续物理安装，2026-10-14

按用户要求，将上述最终 APK 安装到 `192.0.2.1`，通过已有普通账号
`desktop-user` 的 SSH 与 sudo 完成。设备为 x86_64/glibc native-systemd，所有
依赖已安装；该账号原有 subordinate IDs、Podman 组、运行时目录和 linger
已可用，无需重新配置或迁移用户存储。

- 设备现有 APK 签名密钥验证两包通过。离线安装模拟及实际安装仅新增
  `luci-app-podman` 和中文包，没有升级其他包。
- 在新应用的 UCI 白名单中加入 desktop-user；没有修改 rpcd 登录账号或密码。
  设备目前只配置 root 作为 LuCI 登录账号，desktop-user 是 SSH/sudo 账号。
- 实际 RPC info 返回 rootless=true、serviceIsRemote=false、systemd cgroups，
  graphRoot 为 `/home/desktop-user/.local/share/containers/storage`。
  资源列表正常读取，观察到 4 个容器、0 个 Pod、5 个镜像、1 个网络、0 个卷；
  没有对已有容器或其他用户资源执行修改操作。
- 已安装的 RPC 脚本、C 执行助手、任务脚本和前端资源校验值与最终签名包
  payload 一致；两个执行助手均为 root:root、0755，无 setuid 位。
- 受保护的应用 URL 返回预期登录页面；前端资源 HTTP 200。
  未使用未知的 LuCI root 密码登录，因此物理设备上的认证后浏览器页面未在
  本次检查；QEMU 的已登录页面验证见前文。
- network/firewall/dhcp/passwall/luci/rpcd/subuid/subgid 文件 SHA256 与安装前
  相同，启动 ID 不变，procd、uhttpd、rpcd 保持运行。未刷机、未重启设备。
- 临时安装 APK 已移除，SSH 控制连接已关闭。

私有配置备份、安装模拟、安装及验证记录位于
`/srv/openwrt-validation/luci-podman-physical-20261014/`，未保存提供的明文密码。
