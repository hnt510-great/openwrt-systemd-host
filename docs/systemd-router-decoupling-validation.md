# OpenWrt native systemd 纯路由构建与应用解耦验证

验收工作目录：`/srv/openwrt-validation/systemd-router-decoupling-validation-20261119/`。

本轮验证完全在独立 checkout（`/srv/openwrt-validation/systemd-router-decoupling-validation-20261119/checkout`）中使用匹配的本地 feeds 修订和仅受 Git 跟踪的 11 个默认 `files/` 文件完成。主工作区 `/srv/openwrt/.config`（SHA-256 `dcb2fdb46b7fe49c5623bea739eba60a1516945dec093b6300c67b1ff999d821`）、`bin/systemd/`、个人 `files/` overlay 均未修改；未发布 LAN APK feed，也未对实体路由器执行任何操作。

---

## 实现概要

1. **纯路由配置快照与模块化片段**
   - 新增 [configs/x86-64-systemd-router.config](../configs/x86-64-systemd-router.config)（x86_64/glibc/APK/native systemd，UEFI squashfs，含 `kernelctl`、PAM OpenSSH + `openssh-keygen`、`sudo` + 精简 `shadow-*`、LuCI 含中文语言包、`dnsmasq-full`、`odhcp6c`/`odhcpd-ipv6only`、`firewall4`、`ppp` + `ppp-mod-pppoe`、`curl`、`tcpdump` 及 `kmod`/`kmod-nvme`/`kmod-r8169`/`kmod-igc`/`kmod-igb`/`kmod-e1000e`/`kmod-e1000`；显式关闭 `video-support`、普通 `dnsmasq`、`dropbear`、`shadow-all`/`shadow-login` 与安装器 ISO）。
   - 新增可叠加片段：[configs/gnome-desktop-core.config](../configs/gnome-desktop-core.config)（GNOME + RDP + portal，不含 Flatpak）、[configs/podman.config](../configs/podman.config)、[configs/distrobox.config](../configs/distrobox.config)、[configs/virt-headless.config](../configs/virt-headless.config)；保留 [configs/samba4.config](../configs/samba4.config)、[configs/flatpak.config](../configs/flatpak.config) 及完整桌面快照 [configs/x86-64-systemd-desktop.config](../configs/x86-64-systemd-desktop.config)。
2. **GNOME 与 Flatpak 运行时解耦**
   - [package/custom/xdg-desktop-portal/Makefile](../package/custom/xdg-desktop-portal/Makefile)：`PKG_RELEASE` 从 `1` 升至 `5`（避开 [configs/apk-elf-rebuilds.mk](../configs/apk-elf-rebuilds.mk) 中 `1.22.1-r1`/`r2` 已保留的 `1.22.1-r4`），移除 `+flatpak` 运行时依赖，改为构建期通过 `Download/flatpak-interfaces` 从 SHA-256 校验的 `flatpak-1.18.4.tar.xz` 仅提取 `data/org.freedesktop.portal.Flatpak.xml` 并以 `-Dflatpak-interfaces-dir=$(FLATPAK_INTERFACES_DIR)` 传入 Meson，保留 Flatpak 接口代码生成与 `bubblewrap` 沙箱。Flatpak 运行时由 `openwrt-flatpak` 显式引入。
3. **虚拟化与 GNOME 桌面解耦**
   - [package/custom/virt-manager/files/virt-manager-setup](../package/custom/virt-manager/files/virt-manager-setup) 与 [package/custom/virt-manager/Makefile](../package/custom/virt-manager/Makefile)：内联 `virt_manager_validate_user()` 完整保留 UID/GID/主目录/登录 shell/shadow 密码状态检查与 socket/render 授权撤销语义，移除对 `/usr/libexec/desktop-common.sh` 与 `+openwrt-desktop` 的依赖，显式补足 `+shadow-usermod`，`PKG_RELEASE` 从 `4` 升至 `5`。
4. **隔离构建暴露并修复的兼容性问题**
   - **BusyBox 默认 PAM 依赖遗漏**：干净纯路由配置关闭 `CONFIG_BUSYBOX_CUSTOM` 时，`CONFIG_OPENWRT_SYSTEMD` 选中 `CONFIG_BUSYBOX_DEFAULT_PAM=y` 而非 `CONFIG_BUSYBOX_CONFIG_PAM=y`，导致 `busybox` 链接 `libpam.so.0`/`libpam_misc.so.0` 却在打包阶段报错缺少库依赖。已在 [package/utils/busybox/Makefile](../package/utils/busybox/Makefile) 补齐 `BUSYBOX_DEFAULT_PAM:libpam` 与 `+(BUSYBOX_CONFIG_PAM||BUSYBOX_DEFAULT_PAM):libpam` 并升至 `PKG_RELEASE:=16`。
   - **`shadow-login` 与 `busybox` 冲突**：`CONFIG_PACKAGE_shadow-utils=y` 默认开启 `CONFIG_shadow-all=y` 并拉入 `shadow-login`，与 `busybox` 争用 `/usr/bin/login`。已在 `configs/x86-64-systemd-router.config` 关闭 `CONFIG_shadow-all` 与 `CONFIG_PACKAGE_shadow-login`（与完整桌面一致）。
   - **`xdg-desktop-portal` 变量展开顺序**：`FLATPAK_INTERFACES_DIR:=$(PKG_BUILD_DIR)/flatpak-interfaces` 最初位于 `include $(INCLUDE_DIR)/package.mk` 之前导致 `$(PKG_BUILD_DIR)` 为空，已移至 `include` 之后并通过 `prepare` 与完整编译验证。
   - **GNOME 最小组合的 GStreamer 菜单前置**：无 Flatpak 组合 GNOME 时，`libgst1pbutils` 需要 `gstreamer1-libs` 与 `gstreamer1-plugins-base` 处于启用状态才能生成共享库 `.provides`，已固化在 `configs/gnome-desktop-core.config`。
   - **BusyBox `ash` 串口测试兼容性**：精简纯路由镜像不含 `coreutils-stty`/`coreutils-base64` 且默认 shell 为 BusyBox `ash`（交互模式单行编辑上限 512 字节）。已更新 [scripts/test-image-network.py](../scripts/test-image-network.py) 并新增 [scripts/tests/test-systemd-router-pppoe-vm.py](../scripts/tests/test-systemd-router-pppoe-vm.py)，改用短行分片与客体内置 `python3` 处理无回显及编解码。

---

## 纯路由构建产物（内核序列 1，`7.3.5-1-openwrt`）

产物归档于 `/srv/openwrt-validation/systemd-router-decoupling-validation-20261119/artifacts/`：

| 产物 | 路径 | 大小 | SHA-256 |
| --- | --- | --- | --- |
| UEFI 组合镜像 | `artifacts/openwrt-x86-64-generic-squashfs-combined-efi.img.gz` | 44 MiB | `d9ecbed3f3da0ebe59f4f10ea21921b1647add24bd5a8311d7cf1a93d66cf7e3` |
| 根文件系统镜像 | `artifacts/openwrt-x86-64-generic-squashfs-rootfs.img.gz` | 36 MiB | `fdf6c6f8435d9a9133ab979180c125e01fd96b15624fd50ca5c7bec36d57fce0` |
| 安装包清单 | `artifacts/openwrt-x86-64-generic.manifest` | 264 个包 | — |

清单核对确认：`systemd`、`systemd-openwrt`、`systemd-openwrt-services`、`procd`、`ubus`、`netifd`、`firewall4`、`dnsmasq-full`、`odhcp6c`、`odhcpd-ipv6only`、`ppp`、`ppp-mod-pppoe`、`luci`、`openssh-server-pam`、`openssh-keygen`、`sudo`、`shadow-groupadd`、`openwrt-kernel-upgrade`、`kmod-nvme`、`kmod-r8169`、`kmod-igc`、`kmod-igb`、`kmod-e1000e`、`kmod-e1000` 均存在；`openwrt-desktop`、`gnome-*`、`flatpak`、`openwrt-flatpak`、`xdg-desktop-portal`、`podman`、`openwrt-podman-rootless`、`luci-app-podman`、`distrobox`、`samba4-*`、`luci-app-samba4`、`wsdd2`、`avahi-*`、`libvirt-*`、`qemu-*`、`virt-manager`、`luci-app-qemu`、`video-support`、`openwrt-installer`、`dropbear` 与普通 `dnsmasq` 均不存在。

---

## 验证结果

### 1. 源码、Kconfig 矩阵与宿主机单元测试

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| [scripts/tests/test-systemd-router-decoupling.py](../scripts/tests/test-systemd-router-decoupling.py) | 通过（12/12） | 使用隔离 checkout 的最新 Kconfig 元数据执行 `scripts/config/conf --fatalrecursive`，覆盖纯路由、GNOME 无 Flatpak（`gnome-desktop-core.config`）、GNOME 加 Flatpak、Podman 无 Distrobox、Distrobox、Samba 无发现服务、Samba 含 wsdd2/Avahi、无头虚拟化、`virt-manager` 无桌面、完整桌面回归、配方与 `apk-elf-rebuilds.mk` 检查、`busybox` PAM 依赖检查，以及 `virt-manager-setup` 全部 14 组异常/正常用户校验用例 |
| 既有宿主机单元测试（10 组） | 全部通过（196/196） | `test-network-wait-online.py`（14）、`test-systemd-udev-boundary.py`（3）、`test-nas-systemd.py`（8）、`test-samba4-systemd.py`（13）、`test-systemd-service-bridge.py`（29）、`test-custom-package-updates.py`（49）、`test-elf-abi.py`（23）、`test-ucode-abi.py`（6）、`test-merge-usr.py`（9）、`test-kernel-upgrade.py`（42） |
| 隔离包编译与 APK 依赖核验：`virt-manager-5.1.0-r5.apk` | 通过 | 在无 `openwrt-desktop` 的隔离环境中完成编译打包；`apk adbdump` 确认 14 项依赖不含 `openwrt-desktop`，含 `shadow-usermod`、`shadow-groupadd`、`shadow-gpasswd`、`libvirt-daemon` |
| 隔离包编译与 APK 依赖核验：`xdg-desktop-portal-1.22.1-r5.apk` | 通过 | 在确认 `staging_dir/target-x86_64_glibc/usr/lib/pkgconfig/flatpak.pc` 不存在的前提下完成编译打包；Meson 输出 `Build flatpak interfaces: YES`、`Sandboxed image validation: YES`；`apk adbdump` 确认 22 项依赖不含 `flatpak`，保留 `bubblewrap`、`fuse3-utils`、`libpipewire`、`libgst1pbutils`、`libsystemd` 及完整 ELF `so:` 契约 |
| 空白符检查与主 `.config` 完整性 | 通过 | `git diff --check` 无输出；主工作区 `.config` SHA-256 与执行前备份一致 |

### 2. 一次性 KVM/QEMU 虚拟机验证（针对纯路由 UEFI 镜像 `d9ecbed3...`）

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| 双 VM DHCP/DNS/NAT/LuCI（[scripts/test-image-network.py](../scripts/test-image-network.py)） | 通过（9/9） | 证据：`vm-dhcp-network/validation.json`；验证 `systemd` PID 1、路由器服务、`wan-dhcp`、`lan-dhcp`、`dns`、`routing-nat`、`luci-auth`、`luci-http`、`ubus-board`（`OpenWrt Systemd Host` / `7.3.5-1-openwrt`） |
| 冷启动、系统健康与原生 failsafe 恢复（[scripts/tests/test-systemd-router-pppoe-vm.py](../scripts/tests/test-systemd-router-pppoe-vm.py)） | 通过 | 证据：`vm-pppoe-failsafe/validation.json`；验证 `systemd` PID 1、`/overlay` 可写、`openwrt-ubusd`/`openwrt-procd`/`openwrt-services`/`sshd` 运行、`99-multiuser`（`sudo` 组）与 `99-openssh-access`（`sshd -t`）、264 包无无关组件、`kernelctl check`；经 `kernelctl migrate` 切换 `owrt-rescue-failsafe`（`failsafe=true`）启动早期 `init` 控制台，`mount_root` 挂载 `/overlay` 写入标记后普通 `reboot` 恢复至 `systemd` PID 1 |
| 隔离以太网段三 VM PPPoE AC、LAN NAT 与断线重拨（[scripts/tests/test-systemd-router-pppoe-vm.py](../scripts/tests/test-systemd-router-pppoe-vm.py)） | 通过 | 证据：`vm-pppoe-failsafe/validation.json`；一次性 AC 客体仅在测试内安装 `rp-pppoe-common`/`rp-pppoe-server` 并以内核模式 `pppoe-server -k` 提供 PAP 认证与 HTTP 端点；纯路由客体以合成凭据完成发现、认证、建立 `pppoe-wan` 与默认路由；独立 LAN 客户端获取 DHCP 租约与 DNS 解析，经路由器 `fw4` masquerade 访问 AC 上游 HTTP；AC 侧 `killall -TERM pppd` 断线后路由器自动重拨并恢复 LAN NAT 访问 |

---

## 范围与未验证边界

- **主工作区完整桌面构建、发布与实体路由器在线升级（2026-11-19，用户明确授权后执行）**：
  - 在主工作区保持原完整桌面 `.config` 不变（SHA-256 `dcb2fdb46b7fe49c5623bea739eba60a1516945dec093b6300c67b1ff999d821`）执行 `./scripts/feeds update -i custom && ./scripts/build-and-publish.sh -j16`，退出码 0，零错误。内核代际复用第 70 代（`linux-image-7.3.5-70-openwrt`，ABI `7.3.5~adba66b3ab34d0e3afce6489d6e2734a-r1`），ELF 迁移校验覆盖 1387 个包 / 2464 个 ELF 文件全部通过，发布 5 个预期用户态包：`busybox`（`1.38.0-r15 -> 1.38.0-r16`）、`xdg-desktop-portal`（`1.22.1-r4 -> 1.22.1-r5`）、`virt-manager-common` / `virt-install` / `virt-manager`（`5.1.0-r4 -> 5.1.0-r5`）。
  - 实体路由器（`router-admin@192.0.2.1`，`7.3.5-70-openwrt`）执行 `sudo -n apk update && sudo -n apk upgrade` 成功升级上述 5 个包（共 1387 包，零误删）；随后按 `needrestart` 提示重启用户级 `xdg-document-portal.service` 与 `xdg-desktop-portal.service`。复检结果：`needrestart` 报告 0 个受影响服务/进程、`systemctl --failed` 为 0、`kernelctl check` 通过、现有虚拟机 `win2k25` 持续正常运行无需重启。
- **未执行的可选应用运行时 VM 回归**：本轮通过严格 Kconfig 归一化、源码/单元测试及 `xdg-desktop-portal`/`virt-manager` 隔离编译与 APK 元数据核验验证了解耦正确性，但尚未在虚拟机内构建并运行 GNOME 无/含 Flatpak 会话、无桌面 Podman/Samba/libvirt 运行时或 `virt-manager` 图形连接回归测试。
- **未执行的实体硬件与线路验收**：纯路由精简镜像尚未在实体 NIC（r8169/igc/igb/e1000e）、运营商 VLAN 线路与真实 ISP PPPoE 环境下刷机实测。
