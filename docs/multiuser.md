# 普通用户、SSH 与 sudo

当前构建配置包含 Shadow 用户管理工具和 sudo。已有的 OpenSSH 配置允许
普通用户使用密码或各自的公钥登录。公开构建不预设个人账号或密码；
首次启动后请自行创建账号并设置密码。
首次启动会将新密码的默认哈希设为 SHA512，以兼容 Shadow、OpenSSH、sudo
和 BusyBox 登录使用的密码验证实现。

安装并首次启动后以 root 执行，以下以 `alice` 为例：

```sh
useradd -m -U alice
passwd alice
```

这会创建独立用户、同名主组和权限为 0700 的 `/home/alice`。在另一台机器上登录：

```sh
ssh alice@路由器地址
```

包含 zsh 的固件首次启动会将 root 登录 shell 和 `useradd` 默认 shell 设为
`/usr/bin/zsh`。已有普通用户可用 `usermod -s /usr/bin/zsh 用户名` 切换，
重新登录后生效。`/bin/sh` 和 failsafe 恢复 shell 继续使用 BusyBox ash。

需要管理员权限时，root 可将该用户加入 sudo 组：

```sh
usermod -aG sudo alice
```

用户重新登录后即可执行 `sudo -i`，验证的是该用户自己的密码。
未加入 sudo 组的普通用户没有此权限。不要省略 `usermod` 的 `-a`，否则会
覆盖已有的附加组。

使用公钥登录时，将该用户的公钥放在 `/home/alice/.ssh/authorized_keys`。
`.ssh` 目录应归该用户所有、权限为 0700，`authorized_keys` 权限为 0600。
root 的 LuCI 公钥管理路径保持独立。

用户与组数据库（`/etc/passwd`、`/etc/group`、`/etc/shadow`、`/etc/gshadow`、
`/etc/subuid`、`/etc/subgid`、`/etc/default/useradd`）、sudo 配置以及
`/etc/ssh/authorized_keys.d/` 会进入 `sysupgrade -b` 配置备份。出于配置精简
考虑，`files/lib/upgrade/keep.d/multiuser` **不包含** `/home/`（避免将下载、
缓存、容器和浏览器数据打包进配置归档），因此整机重装或离线写盘前请单独备份
`/home/` 及外挂磁盘上的个人数据。x86/64 systemd 单 init 下 `sysupgrade` 仅用于
配置备份、清单与恢复（`-b`/`-l`/`-r`），不再执行整机固件刷写。

这是系统账号支持；LuCI 的账号和 RPC 权限需要单独配置。控制台仍沿用
现有 `ttylogin=0` 设置，自动登录 root。如需控制台也输入用户名和密码，
先确保 root 已设置密码，再执行：

```sh
uci set system.@system[0].ttylogin='1'
uci commit system
```
