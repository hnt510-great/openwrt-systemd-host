# x86/64 systemd 单 init

1. 固定 glibc、APK 和 systemd，保留 OpenWrt preinit 与原生 failsafe。
2. 删除 init 选择器及回退，统一镜像和 kernelctl 生成的 GRUB 菜单。
3. 保留 sysupgrade 的备份、清单和恢复，移除 CLI、ubus、rpcd 和 LuCI 整机刷写。
4. 清理原生单位对应的 recovery 分支，保留仍有调用方的兼容接口。
5. 更新系统身份、构建说明、维护规范和现行测试。每一步记录在 systemd-only-validation.md。

原生 failsafe 的控制台 shell 由 preinit 启动。procd 的服务 API、早期热插拔和 systemd 托管 transient units 是独立能力。kernelctl 的不可变救援内核和正常回退也是独立能力。正常引导与安装器菜单和 kernelctl 动态菜单都需检查。LuCI 的备份与固件刷写共用页面，rpcd 的出厂重置和升级也共用插件，应按功能拆除。单独升级 APK 无法清除旧 squashfs 中的刷写代码，首次迁移使用新镜像并按清单恢复配置。本轮源码和测试验证，VM 验证以后执行。


## 实施与验收细则

- 保留 `bin/systemd` 和现有发行版及 APK 仓库 ID。Kconfig 用常规桌面配置及显式关闭 systemd/APK、选择 musl、关闭 failsafe 的旧配置做严格归一化。其他上游目标源码继续供同步。
- 正常启动保留 preinit、挂载 overlay 和 systemd 预检。预检或 exec 失败时输出诊断并停在早期 init。原生 failsafe 提供控制台、`mount_root` 和重启。
- GRUB 保留原始救援内核、正常 systemd 启动和原生 failsafe。迁移受管理的 GRUB 菜单时保留仍有效的环境变量和试启动计数。
- 配置 CLI 保留 `-b`、`-l`、`-r`、标准输入输出和 `keep.d`。拒绝镜像路径、URL、`-T` 和 force。LuCI 保留清单、导出、恢复和出厂重置。系统维护通过签名 APK 与 kernelctl。
- 配置迁移先核对归档内容并留存旧盘或离线备份，再在新镜像上恢复选定的数据和 unit enable/mask 状态。旧盘可用于离线回退。
- 源码测试覆盖软件包和脚本、严格 Kconfig、GRUB 生成和迁移、配置命令、授权边界。后续 VM 验证覆盖 BIOS/UEFI、安装器、extroot、原生 failsafe、路由和 LuCI、配置跨盘恢复以及 kernelctl 回退。
