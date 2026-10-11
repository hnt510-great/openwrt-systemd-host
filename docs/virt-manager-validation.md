# virt-manager 固件验收与交付

2026-10-11，在本仓库的 x86_64/glibc、原生 systemd 固件中完成
virt-manager 5.1.0 移植及完整镜像验收。最终镜像从全新测试磁盘冷启动，
GUI 验收使用镜像内的软件包，没有在最终测试机中热更新 APK。

## 交付文件

构建目录：`bin/systemd/targets/x86/64-glibc/`。

固件文件：`openwrt-x86-64-generic-squashfs-combined-efi.img.gz`。

```text
SHA256: 5fc6aa02ef9cbd02b08edd45cc7537d95f48458e4fb3c190dc8ae64889c99c4c
文件大小: 351007578 字节
原镜像大小: 335804453 字节
增量: 15203125 字节，约 14.5 MiB / 4.53%
```

不可变镜像副本、207 个应用及依赖签名 APK、公钥、逐文件校验清单和最终
冷启动证据保存在：

`/srv/openwrt-validation/virt-manager-validation-20261011-112759/certified-coldboot/`

其中 `firmware.img.gz` 是镜像副本，`application-apks/` 是签名包，
`application-keys/` 是公开验证密钥，`application-artifact-manifest.json`
记录 APK 大小及 SHA256，`application-signatures.log` 记录签名检查。
该目录还保存测试机磁盘和截图；账号、密钥及测试配置仅存在于测试环境，
不应作为部署配置分发。

## 源码与构建

新增包位于 `package/custom/`：virt-manager、virt-manager-common、virt-install、
libvirt-python、GTK 3、at-spi2-core、gobject-introspection、glib2-gir、PyGObject、
PyCairo、Python libxml2、gtk-vnc、libvirt-glib、libosinfo、osinfo-db、GTK 3 VTE、
dconf、xorriso 和图标资源。GLib 增加 libgirepository-2.0 运行库打包及缓存工具；
Pango、HarfBuzz 和 GdkPixbuf 增加必要 metadata 构建支持。

基础 GLib、host 扫描工具、目标 metadata 分阶段构建。扫描器使用 host Python，
目标辅助程序通过指定 glibc loader 和受控库路径执行。GIR 保存在开发 staging，
固件安装运行所需 typelib；Python 不读取 Debian 的 typelib 或目标运行库。
GTK 3 使用独立库名和包名，不替换 GTK 4 包。GTK 4 应用的同时运行未单独测试。

修复了 GTK 3 对 Weston VNC 动态 seat 的绑定，以及弹出菜单使用错误 seat
输入序号的问题；验证了客户端连接、断开后重连及菜单操作。其他关键修复
包括 libosinfo/libvirt-glib 交叉构建时的 introspection 禁用、Python 扩展的
OpenWrt 构建规则覆盖、缓存安装脚本和 libvirt socket drop-in 排序。

逐层软件包构建及最终 `make -j4 V=s` 成功，完整构建日志为父目录的
`firmware-gtk-fixed-build.log`。207 个匹配 APK 的签名检查通过。
24 个新增相关运行库及 Python 扩展通过 ELF64/x86-64 ABI、RPATH 和目标动态
依赖检查；GTK、GLib、GObject、Gio、Pango、GdkPixbuf、ATK、GtkVnc、VTE、
Libosinfo、LibvirtGObject，以及 cairo/libvirt/libxml2 Python 导入全部通过。
schema、GIO、MIME 缓存及图标资源存在。

构建前保存配置、本地 diff 和相关源码备份。最终审计确认原有 19 处无关
修改保留，原有 CONFIG 选择没有改变，新增 36 个配置项。
详见父目录 `unrelated-changes-preservation-final.json` 和
`configuration-preservation-final.json`。验收阶段没有自动提交、推送或刷写
实体设备；随后经用户要求提交了本次及此前源码改动，见
[local-build.md](local-build.md)。

## 最终镜像实测

| 项目 | 结果与证据 |
| --- | --- |
| 冷启动与普通用户 | 新磁盘启动原生 systemd；自行创建测试账号后从 Weston 图标启动，进程以普通用户运行。`application-identity.log` |
| 授权 | 未授权 GUI 提示 root 命令、原始错误和重试；授权成功；撤销并重启桌面后拒绝；另一个用户仍拒绝。`authorization-before.png`、`revoked-after-host-reboot.png` |
| UNIX sockets | QEMU、storage、secret 的读写/只读客户端 sockets 为 root:libvirt-admin 0660；admin、log、lock 为 root:root 0600；宿主重启后保持。`initial-domain-network-permissions.log`、`host-reboot-persistence.log` |
| 连接失败重试 | 停止 QEMU libvirt 服务和 sockets 后显示具体错误；恢复服务后点击重试成功。`daemon-failure-error.png`、`daemon-retry-success.png` |
| ISO 安装 | GUI 创建 `cert-iso-alpine`，Alpine 3.24.2 ISO 实际安装到 2 GiB qcow2，并从磁盘启动。默认 SeaBIOS、VNC 回环监听和 br-lan。`iso-install-complete.png`、`installed-disk-marker.png` |
| 镜像导入 | GUI 分别创建并启动 `cert-import-qcow2` 和 `cert-import-raw`；显示原磁盘标记，HTTP 可访问。`import-qcow2-console-visible.png`、`raw-import-console.png` |
| VNC 与串口 | VNC 键盘输入完成安装；客体 evdev 记录鼠标移动和按键；GUI VTE 串口登录执行命令并读取磁盘标记。`vnc-mouse-events.png`、`serial-final.png` |
| 硬件与启停 | GUI 关机、将内存 512 MiB 改为 640 MiB、启用 autostart，再从 GUI 启动；domain XML 保存更改。`hardware-panel.png`、`gui-saved-state.log` |
| 目录存储池 | GUI 新建 `/srv/libvirt/test-pool`，停止、启动并启用 autostart；宿主重启后 active/yes。`pool-stopped.png`、`pool-autostart-enabled.png` |
| XML 与设置 | GtkTextView XML 页面可用；GUI 启用 XML 编辑，应用重启后保留；宿主重启前后 dconf 文件 SHA256 相同。`gtk-textview-xml.png`、`preferences-after-app-restart.png`、`host-reboot-preferences-authorization.log` |
| KVM 与路由 | 三个客体的 QMP query-kvm 均为 enabled=true；客体从 OpenWrt dnsmasq 获得 DHCP 地址，经宿主访问软件仓库，并提供 HTTP。`pre-host-reboot.log`、`iso-network-packages.png` |
| 持久化 | 宿主重启后定义及目录池保留，ISO 客体自动启动，内存为 640 MiB，HTTP 返回 FINAL_DISK_MARKER_20261011。`host-reboot-persistence.log` |
| 桌面会话 | 私有 D-Bus 随桌面退出；TLS 证书校验连接成功、错误密码被拒绝；VNC 重连及菜单正常。`desktop-dbus-cleanup-and-revoke.log`、`vnc-authentication.log` |
| systemd 回归 | 路由服务、LAN、timer、socket activation、cgroup 内存/进程限制、journal 与 OpenWrt 日志检查通过。`systemd-router-smoke.log` |
| procd recovery | 同一测试磁盘冷启动 recovery，PID 1 为 procd，LAN/DHCP/LuCI/SSH 正常；最终固件 sysupgrade -T 和配置备份成功。`procd-recovery.log`、`procd-recovery-image-backup-check.log` |

运行检查脚本为 `scripts/tests/virt-manager-smoke.sh`，最终结果保存在
`runtime-smoke.log`。测试账号由测试脚本创建，授权也由 root 显式执行。
安装、授权和应用重启没有删除已有 domain 或存储池定义。

Recovery 检查后再次冷启动原生 systemd，确认 autostart 客体、磁盘标记及
LuCI 认证登录仍正常。最后正常关闭客体和本次 OpenWrt 测试机，停止测试
VNC 客户端；结果见 `acceptance-result.json` 和 `final-shutdown.log`。

## 实测边界与部署注意事项

测试使用隔离的 QEMU/OVMF OpenWrt 宿主，内部客体使用嵌套 KVM 和 SeaBIOS。
外部端口仅绑定宿主回环地址。测试 overlay 将 WAN 改为 DHCP，关闭原测试
环境中的代理/WireGuard，并过滤外层 QEMU DHCP 应答，避免与 OpenWrt DHCP
竞争；这些变更没有写入源 overlay 或交付固件。

本次验证了 Linux ISO、raw/qcow2、本地桥网络、目录池和两个控制台。
没有验证实体 Intel/AMD 机器、真实 PPPoE/物理交换网络、SPICE、UEFI 客体、
设备直通、libvirt NAT 或远程主机管理。Recovery 完成启动、升级格式校验和
备份检查；本次没有执行实际固件刷写。

`libvirt-admin` 权限接近 root。部署授权及撤销命令、会话刷新方法、存储
挂载顺序和升级备份要求见 [virt-manager.md](virt-manager.md) 与
[libvirt.md](libvirt.md)。应分开备份 libvirt 定义、完整客体磁盘和用户 home，
不要将 OpenWrt 配置备份当作虚拟机磁盘备份。
