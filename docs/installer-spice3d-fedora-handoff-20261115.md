# Installer ISO / Fedora SPICE 3D 接手记录 — 2026-11-15

## 当前任务与结论

用户要求 installer ISO 作为 SATA 光盘启动，必须保留 SPICE / VirtIO 3D。先完成本地修改、构建和 VM 验证，用户随后反馈 `ssh remote-host` 上换新 ISO 仍没有输出。最后用户要求停止分析并写接手文档。**不要把本地通过或用户的“好了”当作原 linux2024 的最终显示验收。**

已确认原 Fedora VM 中 Linux、systemd、安装器及 whiptail 都在正常运行；tty1 屏幕缓冲区有完整安装菜单。实际问题在后续图形输出路径。没有证据支持继续重建内核或 ISO 来解决当前黑屏。原 VM 最后一次图形采样仍为黑色，尚未完成最终修复/用户验收。

## 访问方式、环境和边界

- 使用普通 shell `ssh remote-host`，不是 Secure Runner MCP。已连接为 `build-user`。没有核实本次实际采用的认证密钥，不要猜测。
- 用户给过地址 `192.0.2.118`，但该 IP 的 SSH 配置配置用户为 `remote-user`；本次实际成功入口为 `ssh remote-host`，用户 `build-user`。
- Fedora: kernel `7.3.3-300.fc45.x86_64`；QEMU `11.1.3-1.fc45`；libvirt `12.6.0-4.fc45`；virt-manager `5.1.0-5.fc45`；spice-glib / spice-gtk3 `0.43-5.fc45`；spice-server `0.16.0-9.fc45`；virglrenderer `1.3.0-2.fc45`；Mesa `26.2.6-1.fc45`。
- glibc 2.44、glib2 2.90.1、GTK3 3.24.52。SELinux Enforcing。
- GPU `/dev/dri/by-path/pci-0000:72:00.0-render` -> `/dev/dri/renderD128`，AMD 设备 1002:13c0。
- 不重启/修改原 `linux2024`，不重启桌面、virt-manager、libvirt。没有安装 Fedora RPM，没有改系统客户端库，没有关闭全局 SELinux。
- 需要原 VM 关机、重启或已有客户端重开时，先取得用户明确授权。可继续使用独立空盘测试机做定位；不要触碰 win11 或用户磁盘。

## 镜像与已完成的本地修改

新镜像（独立名称，原默认 ISO 保留）：

`bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-installer-spice3d.iso`

SHA256：`5cd77086f22f62411bb5bcb3f29563f6d6346087f045fe86bff4315430d14844`，958369792 bytes。

Fedora 挂载的是 `/srv/openwrt-validation/iso/openwrt-x86-64-generic-installer-spice3d.iso`，**现场 SHA256 完全相同**。

这是原 clean squashfs 离线更新三个构建 APK 后，用现有 ISO builder 封装的定向镜像；不是全量固件重建。内核仍 `7.3.4-63-openwrt`，内核字节未变，没有新内核代次或模块 ABI 混用。

工作树本任务修改（全部未提交）：

- `package/base-files/files/lib/preinit/99_10_run_init`：可选网络清理之后显式 return 0，避免无 NIC 时 preinit 返回 1 导致跳过 systemd handoff。`package/base-files/Makefile` release `.15` -> `.16`。
- `package/custom/openwrt-installer/files/openwrt-installer@.service`：ExecStartPre dmesg -n 4，避免 warning 覆盖菜单；installer release 2 -> 3。
- `package/custom/spice-gtk/patches/003-redraw-imported-gl-scanout.patch`：already-ready widget 导入 scanout 后排队重绘；导入失败直接 return。spice-gtk release 2 -> 3。经 quilt 和 package refresh 生成；001、002 原补丁内容已保留。
- 新测试 `scripts/tests/test-preinit-handoff.py`、`scripts/tests/spice-gl-console.py`。
- 文档 `docs/installer-iso.md`、`docs/installer-iso-validation.md`、`docs/spice-egl-build-validation.md`。

注意：现有文档记录的本地通过不代表 Fedora 原 VM 问题已解决。宿主机客户端修复不会因为客体换 ISO 自动生效。

本地已验证：preinit 3 tests；installer 9 tests（host UCI 一项 skipped）；optical 实际 prepared root 的 2 tests 均通过；三包构建通过；spice fresh patches 零 fuzz 且与编译源一致。相同新 ISO 的 BIOS+VirtIO NIC、BIOS 无 NIC、OVMF+VirtIO NIC 均进入安装器；各自 VirGL shader readback `17,204,51,255`、SPICE Down/Up、两次 passive reconnect 通过。没有执行安装/格式化。

本地证据根目录：

`/srv/openwrt-validation/installer-spice3d-validation-20261115/`

其中 `final-receipt.json`、`final-vm-tests.log`、`verify-final.py`、`start-vm.py`、`final-assemble-command.json` 及 `final-{bios,offline,uefi}-spice/` 可复查。源码/构建日志见上述 validation 文档。本地测试 VM 和私有 chroot bind mounts 已全部清理。

## Fedora 原 VM 现场证据

- `qemu:///system`，domain `linux2024`，最后 ID 7，UUID `00000000-0000-0000-0000-000000000000`（不是最早用户贴的旧 UUID）。
- Q35 11.1 / BIOS / 4 vCPU / 4 GiB，virtio 磁盘 `/var/lib/libvirt/images/linux2024.qcow2`，SATA CD-ROM 第一启动；VirtIO NIC 桥接 br0。
- virtio-vga-gl + 3D yes，graphics 仍为 address / 127.0.0.1 / autoport，实际 TCP 5900；virt-manager 通过 libvirt openGraphicsFD 建立的各 SPICE channel **实际是 Unix socket**。因此不能只根据 XML 的 address 断言在使用 TCP 传 GL FD。
- QEMU log `/var/log/libvirt/qemu/linux2024.log` 有 `no gl-draw-done within one second`、旧次运行的 `no gl-unblock within one second`。
- 系统客户端 `SpiceClientGLib.Session().get_property('gl-scanout')` 为 True，不能归因为未编译 EGL。
- 原 virt-manager PID <pid>，没有被本 agent 重启。其日志 `~/.cache/virt-manager/virt-manager.log` 有 hoststorage NoneType 异常，但还没证明与显示问题有关。
- 通过串口确认 `/proc/1/comm=systemd`，`openwrt-installer@tty1.service=active`，tty0 active=tty1。
- `/dev/vcs1` 有 Welcome / Install OpenWrt / Open shell / Reboot 菜单。DRM state：plane0 fb44，fbcon 分配，1280x800，XR24，CRTC active。
- Guest `CONFIG_FB_DEVICE` 未启用，所以 `/proc/fb`、`/sys/class/graphics/fb0/blank` 不存在本身不是失败。
- QMP screendump `no surface` 本身也不能诊断 GL 黑屏。

串口 libvirt NONBLOCK stream 首次采样容易没有数据/延迟拿到上一批输入；recv 可返回整数 -2，不能直接当 bytes 拼接。后来直接以 sudo Python 打开 `/dev/pts/2`（需先从 XML 核实当前 PTY，不要硬编码继续使用），O_RDWR|O_NOCTTY|O_NONBLOCK，写 CRLF 并 select/read 约 5 秒，成功得到完整交互输出。

对原 guest 仅做过诊断输入：回车/读取命令、Down、Alt+SysRq+T 打任务栈、`kill -WINCH 1352; chvt 2; sleep 1; chvt 1` 触发菜单/VT 重绘。1352 是当时 whiptail PID，**后续必须重查**。未输入安装确认。SysRq 警告曾覆盖菜单，不能将该采样当成 pristine 菜单。

## 私有修复客户端及图像证据

Fedora 私有目录：

`~/.local/share/openwrt-spice3d-test-20261115/`

只在此处放了本地构建的两个 spice .so 和 soname symlink（`lib/`）、诊断 Python、测试盘/XML/日志/PNG。以 LD_LIBRARY_PATH 仅影响新诊断进程，不是系统安装。Fedora glibc/GLib 比构建目标新，ldd 无缺失，实际私有库可加载；用 Fedora 原生 GTK/Mesa。

- `viewer.py [domain]`：通过 libvirt openGraphicsFD，分别打开 SPICE channel，GTK 显示，周期抓取真实 GL framebuffer。后加了 glGetTexImage 导出导入纹理并统计颜色。
- `spice-gl-console.py`：从仓库复制的自动上下键、截图、两次无输入重连测试。
- 环境：XDG_RUNTIME_DIR=/run/user/1000，WAYLAND_DISPLAY=wayland-0，GDK_BACKEND=wayland，LD_LIBRARY_PATH 指向上述 lib/。X11 也试过，DISPLAY=:0、XAUTHORITY 当时 `/run/user/1000/.mutter-Xwaylandauth.LHRKY3`，不要认为后续路径不变。
- 原 linux2024 使用私有修复库的 Wayland 和 X11 viewer 都仍黑屏。其导入纹理 1280x800，glGetTexImage 无 GL 错误，但只有一个颜色 `(0,0,0,255)`。这是比仅“窗口黑”更强的证据；单纯重绘补丁尚不足以解决原 VM。
- DMA-BUF scanout：一 plane，stride 5120，offset0，format 875708993（AR24），modifier 72057594037927935（INVALID）。尝试 mmap FD 返回 EPERM，尚未证明是 SELinux；不要擅自放开策略。
- 后续控制 VM 的纹理有 4 种颜色，源 alpha 多为 0，但 GTK framebuffer 最终 alpha=255且有菜单颜色。不要仅根据源 alpha=0 下结论。
- 某些截图出现部分菜单/缺少边框，**仍需检查是否完整/稳定**，不能只用“有四种颜色”当全面验收。
- 诊断 viewer 可能挤掉原 virt-manager 的 SPICE 会话。原 app 进程没重启；继续时需确认其实际连接状态。

## Fedora 控制实验与尚未排除的分支

1. **相同 Fedora、相同 ISO、直接启动 QEMU 的独立空盘 VM**：正常显示完整菜单。`probe-native-idle/` 的测试在启动稳定后运行，上下键改变选择，Up 返回初始画面，两次重连图像与 Up 相同。证明 Fedora GPU/驱动/QEMU 与该 ISO 的组合能够显示，并非只能在本地 Debian 成功。
2. 同样直接 QEMU，添加与 libvirt 相同的 seccomp sandbox 参数（obsolete/elevateprivileges/spawn/resourcecontrol deny）：也获得彩色菜单并完成检查。首次测试开始较早，有些截图覆盖 boot -> menu 过渡；不应将其所有 SHA 差异归因为按键。不能据此认定 sandbox 是根因。
3. `probe-blob`（blob=true,hostmem=268435456）创建过，但**未完成验收**，已经停止；不要声称 blob 修复了问题。
4. libvirt 临时克隆 `installer-gl-isolated-selinux`：来自原 inactive XML，但新 UUID/空盘、去 NIC、SPICE listen none、仅该测试 VM seclabel type none。出现彩色菜单纹理/部分菜单，原 VM 黑屏未改善。
5. libvirt 临时克隆 `installer-gl-listen-none`：来自原 inactive XML，新 UUID/空盘、去 NIC、SPICE listen none，**保留正常动态 SELinux**。也有彩色菜单纹理，最新状态 draws22 / scanouts1 / ready true / GL error0 / texture4 colors。因此没有依据要求全局关闭 SELinux。

实验 4/5 同时改变了 fresh boot、空盘、NIC 和 listen，且初次连接客户端状态也不同。**尚未隔离 listen none 是否单独足以修复原 VM，或原 VM 早期未确认 GL draw 导致持久坏状态。** 下一步优先在独立 clone 做单变量对比：address 与 none、stock 与私有客户端、首次连接时机；稳定进入菜单再运行输入/重连测试。若最后需要改原 VM 的 listener 或重启，先备份 inactive XML并取得授权。

## 停止时的清理状态

本次写交接前已停止自己的诊断 viewer PID <pid> 和两个临时 libvirt domain（上述两个 installer-gl-*），它们是 transient 定义；XML/空盘文件保留，可复现。

直接 QEMU 的 probe-native / probe-blob / probe-sandbox 早已通过自己的 QMP quit 停止。不要根据旧 PID 杀进程，必须检查命令行。原 linux2024 仍 running，未被重启；win11 未动。没有留下 chroot bind mounts在 Fedora（该阶段未使用 chroot）。

远端保留文件：`selinux-isolated.xml`、`listen-none.xml`、两份 `installer-gl-*-final.xml`、各 qcow2、probe command JSON、serial/qemu logs、viewer logs、status.json、texture.png、screen.png、probe-native-idle/ 等。

## 本地 Fedora 证据副本

`/srv/openwrt-validation/installer-spice3d-validation-20261115/fedora/`

- `linux2024-inactive.xml`：原 VM inactive 配置。
- `remote-evidence.tar.gz`：清理前远端私有诊断目录快照，排除 lib/、qcow2、source.raw；含脚本、XML、JSON、日志和 PNG。
- `guest-kernel-log.txt`、`guest-tasks.txt`：原 guest 内核 printk 环形缓冲区/任务栈读取。
- `patched-client.png`、`patched-after-key.png`、`patched-x11.png`、`after-vt-redraw.png`：原 VM 黑屏采样。
- `direct-probe.png`：Fedora direct QEMU 的完整菜单。
- `libvirt-isolated.png`：临时 clone 的部分菜单采样。

内核环形缓冲区是通过精确本地 vmlinux 的 `__log_buf` 地址 `0xffffffff83534b78`，HMP `x /131072bx ...` 读取，使用 `libvirt_qemu.qemuMonitorCommand`（不是 virDomain.qemuMonitorCommand）。本次没有 KASLR 偏移，CPU RIP `ffffffff8205159b` 对应 pv_native_safe_halt。不要跨镜像/启动假设地址不变。原域因此带有 libvirt custom-monitor taint，这不是另外的启动错误。

## 工作树保护与剩余文档工作

先读 GEMINI.md、docs/project-state-20261114.md。当前未提交状态还包括用户原有 needrestart 四文件修改、Argon 子模块脏状态和原来的 untracked 文件/缓存；必须保留，不能整体 reset/clean/stage。未 commit/push、未发布 feeds。

现有三个 feature/validation 文档主要写了本地通过，还没有加入本次 Fedora 结论；可基于本接手记录补充，并明确本地通过、Fedora direct QEMU 通过、原 linux2024 尚未验收这三个边界。
