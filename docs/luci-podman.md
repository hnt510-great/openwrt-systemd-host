# LuCI Rootless Podman

源码位于 `package/custom/luci-app-podman`。参考本树
`luci-app-dockerman` 的页面划分，使用独立的 `luci.podman` RPC 后端；
不依赖 Docker daemon 或 Docker API socket。

服务菜单中的 **Rootless Podman** 提供：

- 概览：版本、rootless 状态、cgroup、运行时和实际存储目录。
- 账号选择：在已允许的普通用户间切换，各用户的存储相互独立。
- 容器：创建、启动、停止、重启、暂停、恢复、删除、详情及最近 200 行日志。
- Pod：创建、启动、停止、重启、删除和详情。
- 镜像：列表、后台拉取、详情和删除。
- 网络和存储卷：列表、创建、详情和删除。
- 简体中文界面，资源列表每 10 秒刷新。

## 配置账号

先按 [Rootless Podman](podman-rootless.md) 配置已有普通账号：

```sh
podman-rootless-setup alice
```

通过 SSH/PAM 登录该用户以建立运行时目录。native-systemd 下，持续使用
LuCI 管理时可以由管理员启用用户 linger：

```sh
loginctl enable-linger alice
```

在 LuCI 的 **服务 → Rootless Podman → 配置** 选择允许管理的账号，保存应用。
也可以明确配置 UCI 白名单：

```sh
uci add_list luci_podman.main.users='alice'
uci commit luci_podman
```

新安装默认白名单为空。应用不创建账号、不自动分配 subordinate IDs，也不
自动开启 linger。配置文件 `/etc/config/luci_podman` 在包升级时保留。

账号需要 UID ≥ 1000、非零主 GID，以及每个命名空间至少 65536 个
subordinate IDs。执行助手进一步检查 `/run/user/<UID>` 的类型、所有者和
权限；缺少运行时目录时返回明确错误，不改用 root 或临时目录。

## 创建资源

镜像拉取使用完整名称，例如 `docker.io/library/alpine:3.23`。
容器创建仅使用本地已有镜像，不会在创建时隐式拉取。新容器先处于停止状态，
之后点击启动。

命令参数每行一个，无需 Shell 引号。例如运行 `sleep 3600`：

```text
sleep
3600
```

端口格式为 `8080:80/tcp`，环境变量为 `KEY=value`，卷为
`data:/data:rw` 或 `/home/alice/data:/data:ro`，均可每行填写一项。
主机可能限制 rootless 使用低于 1024 的端口。重启策略不配置开机自启；
开机启动需另行配置用户服务。

Pod 默认不创建 infra 容器，也不共享命名空间，仅将容器分组。
先创建 Pod，再创建容器并填写 Pod 名称，之后可按 Pod 启停。
要共享网络、IPC 和 UTS，填写 infra 镜像及所需的启动命令。
例如测试用的已缓存 Alpine 镜像可配合 `/bin/sleep 600`；生产环境应使用
适合长期运行的 infra 镜像和命令。

当前固件的 Podman 5.8.4 在启动内置 infra 根文件系统时可能报 overlay
`invalid argument`；显式使用镜像可避开该问题，应用不修改用户的存储配置。

删除操作需要页面确认，不使用 `--force`，不执行 prune 或 system reset。
正在使用的资源由 Podman 拒绝删除。当前界面覆盖上述常用操作，不提供终端、
Compose、镜像构建/导入/推送或容器配置编辑。

## 后端与权限

rpcd 只接受固定方法和动作。资源名、镜像名和创建参数经过验证，再按独立
参数传递，客户端不能选择可执行程序、全局 Podman 参数或任意 root 命令。
`podman-luci-exec` 是普通 0755 文件，没有 setuid 位；它只能由 root 调用。
在执行 `/usr/bin/podman --remote=false` 之前，助手先初始化用户补充组，
降低真实及有效 UID/GID，清空继承环境，再设置账号的 HOME、运行时目录及用户总线。
用户自己的标准位置容器/存储配置继续生效。

ACL 将只读方法与修改方法分开；只读页面不显示修改按钮。白名单授权的是
LuCI 管理员对选中系统账号的访问，并非每个 LuCI 登录账号的独立租户隔离。
日志和详情作为文本显示。

修改操作作为后台任务执行，运行最长 300 秒，输出有大小限制。
任务目录为 root 所有的私有临时目录；客户端通过随机任务 ID 查询结果，
查询同时检查账号和目录所有者。关闭对话框不取消任务。
后续修改请求会清理超过一小时的任务目录。

## 构建与验证

```sh
make package/custom/luci-app-podman/compile V=s \
  CONFIG_PACKAGE_luci-app-podman=m CONFIG_PACKAGE_luci-i18n-podman-zh-cn=m
python3 scripts/tests/test-luci-podman.py
node scripts/tests/test-luci-podman-view.js
```

当前 x86_64/glibc native-systemd 产物：

```text
bin/systemd/packages/x86_64/base/luci-app-podman-1.0.0-r1.apk
bin/systemd/packages/x86_64/base/luci-i18n-podman-zh-cn-0.apk
```

安装到有匹配依赖的 OpenWrt 系统：

```sh
apk add /tmp/luci-app-podman-1.0.0-r1.apk /tmp/luci-i18n-podman-zh-cn-0.apk
```

若要编入固件，在 menuconfig 选择上述包，再构建镜像。
应用开发阶段没有更改已有 `.config`。后续物理设备安装情况见验证记录。

实际验证结果见 [验证记录](luci-podman-validation.md)。
