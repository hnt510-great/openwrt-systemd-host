# systemd 单 init 实现验证

- 方案与现有启动、刷写及迁移边界已记录。

- 构建配置锁定 x86/64 的 glibc、APK、systemd 和 failsafe。镜像及 kernelctl 菜单已移除 procd 项。

- preinit 正常路径交接 systemd，交接失败停在早期 init。保留原生 failsafe shell，移除该镜像的 failsafe 等待刷写。

- 已加入配置专用 sysupgrade 构建路径，移除 native 刷写程序及 RPC 注册，并精简 LuCI 页面与权限。

- 已将已识别的原生服务改为构建时安装 systemd 转发脚本，删除 APK resume 和 GNOME 的 recovery 路径。

- procd 和 rpcd 的完整补丁链已针对缓存中的原始源码以零 fuzz 应用。

- 严格 Kconfig 已验证桌面和带旧关闭值的最小配置，均得到 glibc、APK、systemd 和启用的 failsafe。kernelctl 配置生成相关用例、备份元数据 3 项、控制台 2 项通过。LuCI JS 与 ACL 语法检查通过。

- 原生服务的转发和安装钩子测试通过，分别为 auxiliary 6 项、NAS 8 项、Samba 13 项、OpenSSH 16 项。配置专用 CLI 边界测试通过 2 项。
- OpenWrt 目标交叉编译器通过修改后的 procd/rpcd C 源码语法检查。
- 已更新系统元数据、构建说明和主要维护规范。

- kernelctl 增加旧菜单迁移用例，通过全部 42 项测试。三个改动 feed 的补丁可逆向检查，基线与补丁路径已写入 configs/systemd-only-feeds.json。

- 重新生成包元数据后通过严格 Kconfig。最小旧配置显式选择 Attended Sysupgrade 或 owut 时，正式配置仍排除它们。
- 隔离目录中完成 init、procd、rpcd 和 rpcsys.so 的交叉编译与链接，二进制检查确认刷写 RPC 已移除。


## 本轮测试结果

- 14 组主机测试共 168 项，166 通过，2 跳过。跳过项为旧 staging rootfs 的已安装镜像覆盖检查，以及缺少 host UCI 的安装器用例。
- 主仓及三个改动 feed 通过 `git diff --check`。三个 feed 补丁从清单基线验证可应用，并在现有工作树验证可逆向应用。
- 完整 APK/固件镜像、GRUB 实机启动、原生 failsafe 和跨盘配置恢复仍需用新镜像验收。本轮未启动 VM，也未发布或修改实体设备。

## 完整固件构建与 VM 验证

验收工作目录：`/srv/openwrt-validation/systemd-only-validation-20261118/`。本轮仅执行本地 `build-only` 构建与一次性 QEMU/KVM 虚拟机验证，未发布 LAN APK feed，也未操作实体设备。

### 构建与 VM 验证期间修复的问题

1. **ELF 迁移保留版本冲突**：`feeds/packages/utils/dbus/Makefile` 原递增至 `PKG_RELEASE:=10`（`1.16.2-r10`），`feeds/packages/utils/podman/Makefile` 递增至 `PKG_RELEASE:=3`（`6.1.2-r3` 经 `configs/apk-elf-rebuilds.mk` 映射为 `6.1.2-r4`），分别与 `configs/apk-elf-rebuilds.mk` 已保留的迁移版本冲突。已将 `dbus` 调整为 `PKG_RELEASE:=11`、`podman` 调整为 `PKG_RELEASE:=5`，并同步更新 `patches/feeds/0046-packages-systemd-only.patch` 与 `packages` feed 索引。
2. **`base-files` 构建期 `sysupgrade` 裁剪表达式转义**：`package/base-files/Makefile` 在 `BuildPackage` 二次展开中 `$$` 退化导致 `sed` 报错退出。已改为 `$$$$` 并展开 `rm` 花括号路径，同时更新 [scripts/tests/test-systemd-backup-cli.py](../scripts/tests/test-systemd-backup-cli.py) 对 `Makefile` 表达式的提取逻辑。
3. **`dbus-native.init` 重启语义回归**：虚拟机内运行 `boot-readiness-guest.py` 发现 `/etc/init.d/dbus restart` 会重启 `dbus.service` 导致系统总线 PID 改变。已恢复 [dbus-native.init](../feeds/packages/utils/dbus/files/dbus-native.init) 对 `boot|stop|shutdown` 空操作、`start|restart|reload` 幂等执行 `systemctl start dbus.service` 的语义，并同步更新 `patches/feeds/0046-packages-systemd-only.patch` 与重建镜像。

### 最终构建产物（内核序列 70，`7.3.5-70-openwrt`）

| 产物 | 路径 | SHA-256 |
| --- | --- | --- |
| UEFI 组合镜像 | `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz` | `79f0ef3936beec343316f0d758542a17065b57492ee1509491829bc34614b3f2` |
| 混合安装器 ISO | `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-installer.iso` | `5af7387b0e5acfdba191ed0d10664fa8c7efe33866499e57ff0f542c3d569ab1` |
| 根文件系统镜像 | `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-rootfs.img.gz` | `9ec0d8d323e7d74872bbc102a9f8e058707f54bd1a4d3be4fe2982241db20abd` |

### 最终编辑后的主机与 VM 验证结果

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| 主机服务/系统单元测试（11 组） | 通过（1 项因缺 host UCI 跳过） | 含 `test-systemd-backup-cli.py`（2）、`test-kernel-upgrade.py`（42）、`test-auxiliary-systemd.py`（6，含新 staging rootfs 校验）、`test-nas-systemd.py`（8）、`test-samba4-systemd.py`（13）、`test-sshd-systemd.py`（16）、`test-systemd-service-bridge.py`（29）、`test-procd-units.py`（9）、`test-network-wait-online.py`（14）、`test-systemd-udev-boundary.py`（3）、`test-openwrt-installer.py`（11/12，1 skipped） |
| 主机 ABI/打包工具测试（5 组） | 全部通过 | `test-elf-abi.py`（23）、`test-ucode-abi.py`（6）、`test-custom-package-updates.py`（49）、`test-merge-usr.py`（9）、`test-alternatives.sh` |
| 仓库空白符与 feed 补丁可逆向校验 | 通过 | 主仓及 `packages`/`luci`/`taskplan` 通过 `git diff --check`，`0046`–`0048` 均通过 `git apply --reverse --check` |
| 双 VM 路由与 LuCI 验证（`scripts/test-image-network.py`） | 通过（9/9） | 证据：`image-network-final/validation.json`；验证 `systemd` PID 1、WAN/LAN DHCP、DNS、NAT 转发、LuCI HTTP 登录、ubus 鉴权与 `system board`（`OpenWrt Systemd Host` / `7.3.5-70-openwrt`） |
| 安装器 ISO 与 BIOS/UEFI/extroot/F2FS 验证（`scripts/tests/test-installer-iso-vm.py --case all`） | 通过 | 证据：`installer-iso-final/receipt.json`；覆盖混合 BIOS/UEFI ISO、`grub.cfg` 无 `openwrt.init=`/recovery 项、case `a`（OVMF + NVMe + ext4 + DHCP/IPv6 + GNOME + `kernelctl` bootstrap + LAN 客户端）、case `b`（BIOS + SATA + btrfs + static）、case `c`（OVMF + virtio + xfs + PPPoE + fullcone）、`extroot` 回归及组合镜像内部 F2FS 回归 |
| `systemd-only` 专项 VM 行为验证（`verify-systemd-only-vm.py`） | 通过（4/4） | 证据：`vm-suite/receipt.json`；覆盖：（1）运行时/CLI/ubus（`system` 与 `rpc-sys` 无刷写接口、`factory` 保留）/LuCI `flash.js` 与 ACL 边界、`grub.cfg` 清理、已移除固件刷写路径及 `systemd-guest-smoke.sh` + `boot-readiness-guest.py`；（2）`owrt-rescue-failsafe`（`failsafe=true`）启动、`init` 早期控制台、`mount_root` 挂载 F2FS `/overlay` 写入标记及不带 `-f` 的 `reboot` 恢复至 `systemd` PID 1；（3）`sysupgrade -b` 到独立新盘 `sysupgrade -r` 跨盘配置、自定义文件及 `systemd-oomd.service` mask 状态恢复；（4）`kernelctl migrate` 清理旧 `owrt-*-procd` GRUB env、注入坏内核（`init=/bin/false panic=1`）触发 3 次计数回退至 `owrt-rescue` 及显式 `kernelctl set-default` + `kernelctl rollback` |
| P0-1 补跑：修改过的客体/VM 测试脚本（10 组） | 全部通过 | 证据：`p0-1/uci-history/validation.json`、`p0-1/daed/validation.json`、`p0-1/in-guest/receipt.json`。<br>独立 KVM 用例：`test-uci-history-vm.py`（13/13）与 `test-daed-vm.py`（28/28）通过。<br>客体内用例：`auxiliary-systemd-guest.py`、`nas-systemd-guest.py`、`samba4-systemd-guest.py`、`sshd-systemd-guest.py`、`logd-journal-guest.py`、`procd-units-guest.sh`、`podman-systemd-guest-smoke.sh`（根模式，未传普通用户）与 `systemd-service-bridge-guest.py`（`--disposable` 重启后 `--after-reboot --network --reconnect`）全部通过。<br>同步修正了 3 个仍残留旧假定的客体脚本：（1）[sshd-systemd-guest.py](../scripts/tests/sshd-systemd-guest.py) 改为验证 `sshd-native.init` 转发 `systemctl` 且 `openwrt@sshd.service` 仍被桥接拒绝；（2）[logd-journal-guest.py](../scripts/tests/logd-journal-guest.py) 保留 `1 KiB` 防崩溃验证，并将重启回填检查改为 `4 KiB` 以容纳 `systemd` 单位重启生命周期日志；（3）[systemd-service-bridge-guest.py](../scripts/tests/systemd-service-bridge-guest.py) 将 `--network` 对已迁出桥接的 `openwrt@cron` 检查改为原生 `cron.service` 与 `openwrt@odhcpd` |

## 实体路由器迁移与验收（2026-11-18）

从 `7.3.5-69-openwrt` 在线执行已发布的签名 APK 升级。APK 事务成功，第
70 代成为待试启动内核，路由器继续运行第 69 代，直至使用新盘开机。

### 换启动 U 盘并保留 NVMe extroot

- 目标是 29.3 GiB 新 U 盘。旧盘是 57.7 GiB，因此在新盘重建可容纳的 GPT
  布局，继承旧盘的分区标识，复制升级后的启动分区与 GRUB 启动数据。新盘
  的默认项为 `7.3.5-70-openwrt`，回退项为 `7.3.5-69-openwrt`。
- fstools 按 squashfs 超级块的 `bytes_used` 向上对齐 64 KiB，定位根分区内
  的 F2FS。旧镜像起点是 `564461568` 字节，本次新镜像是 `947060736`
  字节。先在新位置创建 F2FS，在 `upper/etc/config/fstab` 预置原 NVMe
  extroot 的文件系统 UUID，再仅写入该边界之前的 squashfs 数据。完整解压
  的根文件系统镜像包含尾部填充，整段写入会覆盖已预置的 F2FS。
- 用户在路由器上执行有写入边界检查的脚本，共写入 `947060736` 字节。
  换盘前只读挂载检查通过，确认 UEFI 引导文件、第 70 代内核和 initramfs、
  GRUB 环境、新 squashfs 及 F2FS 的 extroot 配置。新旧盘共享分区标识，
  用户换盘开机前拔掉了旧盘。
- 实际启动后，PID 1 为 systemd。`/rom` 和 `/boot` 来自新 U 盘，
  `/overlay` 仍是原来的 `/dev/nvme0n1p1`。第 70 代已成为运行、默认和
  已知良好内核，试启动计数已清除。LAN 和 WAN 均已上线。

### 启动后的修复与待查项

- **旧救援模块**。首次实机检查发现 `legacy-6.18.55` 的 372 个模块清单
  路径中缺少 362 个。旧模块原本由旧 squashfs 提供。按救援清单从本机只读
  挂载的旧 U 盘取出这 362 个文件，核对内容后复制到路由器的
  `/usr/lib/modules/6.18.55/`。随后 `kernelctl check` 返回 0，且
  `modprobe --set-version 6.18.55 --show-depends 9p` 能解析依赖。
  尚未实际启动旧救援内核。
- **Hermes ACL**。首次启动时，Hermes 对仅存在于只读 squashfs 的 SmartDNS
  文件设置 ACL 失败，导致刷新中断。路由器上的 Hermes 脚本增加了窄范围
  重试，对已通过原有筛选的普通文件触发 OverlayFS copy-up，再设置只读 ACL。
  连续两次刷新成功。两份 SmartDNS 文件与 `/rom` 内容一致，Hermes 可读
  且不可写。修复未重启 SmartDNS。
- **启动分区 FAT 告警**。新盘启动时报告前次未正常卸载。在线逐块复制旧
  `/boot` 可能带入 FAT 未卸载标记。后续日志没有这块启动盘的 I/O
  错误，内核及引导文件校验通过。下次维护时，确认启动分区已卸载后可用
  `fsck.fat -n` 做只读检查。本次未执行 fsck。
- **NVMe 与日志恢复**。EXT4 清理了两个遗留 inode，记录了
  `recovery complete`，随后以读写方式挂载，`errors_count=0`。
  journald 替换了五个未正常关闭或损坏的旧日志，并继续写入新日志。
  前一次日志记录了关机流程，但未记录完整的卸载收尾。其他 Generic USB
  设备的 I/O 错误与这块启动盘及 NVMe 分开记录。
