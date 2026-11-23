# OpenWrt 桌面包解耦实施计划与交接

2026-11-23，已完成设计与源码核对，待实现。基线是 `1a6def2a22`（会话切换器和 LuCI 桌面控制），接手时先重新确认 HEAD 和工作树。当前仓库内 `openwrt-desktop` 配方为 release 40。详见[本轮基线的验证记录](desktop-session-switcher-validation.md)。

## 目标与范围

桌面公共层、LuCI、音频、Fcitx5/Pinyin 基础、Flatpak、AppImage 和 Sunshine 可独立安装，APK 依赖闭包中无 GNOME 专用组件。现有 GNOME 用户仍能从原包名滚动升级，保留桌面配置、密钥和远程服务行为。GNOME 是本期唯一正式桌面后端。用测试会话验证公共层，Plasma 移植和第二桌面安装选项留作后续项目。本期对同一组件 ISO 只做与包拆分相关的调整。

## 现状与迁移风险

| 当前证据 | 对实施的影响 |
| --- | --- |
| [`openwrt-desktop` 配方](../package/custom/openwrt-desktop/Makefile) 的 `-core` 直接依赖 GNOME Shell、Keyring、GNOME Portal 和桌面应用。LuCI、音频、IME、Flatpak 和 AppImage 都直接依赖 `-core`，Sunshine 经音频间接依赖它。 | 仅增加 `sessions.d` 插件可以接入启动器，但不能消除 APK 的 GNOME 依赖。`openwrt-desktop` 已是包含 `-core` 和 `-rdp` 的兼容入口，组件 ISO 可单装 `-core`。 |
| [`desktop.init`](../package/custom/openwrt-desktop/files/desktop.init)、[`desktop-session`](../package/custom/openwrt-desktop/files/desktop-session) 和 [`desktop-ctl`](../package/custom/openwrt-desktop/files/desktop-ctl) 默认选 `gnome`，共同依赖 `/etc/desktop/gnome/<UID>.keyring-passphrase[.cred]`，控制器还直接探测 `gnome-remote-desktop.service`。 | 包可以拆开，但如果保留这些全局启动条件，无 GNOME 的会话仍无法启动。Keyring 在普通用户会话里解锁，凭据由 systemd 系统管理器注入。保留 TPM2 SRK 和现有明文回退语义、文件权限及凭据保密边界。旧设计复用 GNOME Keyring 的建议只适用于兼容过渡。 |
| [`desktop-gnome-remotes`](../package/custom/openwrt-desktop/files/desktop-gnome-remotes) 等待 Mutter 和 `WAYLAND_DISPLAY`，目前兼管音频、Flatpak、RDP 和 Sunshine。Flatpak helper 写死 `XDG_CURRENT_DESKTOP=GNOME`。Sunshine 在 `gnome-session.target.wants/` 中查找 `app-dev.lizardbyte.app.Sunshine.service` 的启用链接。 | 包依赖改完还要移接启动、停止和 LAN 地址变化后的重绑。旧启用链接是实际用户状态。Flatpak 应使用当前会话环境，PipeWire 的屏幕共享依赖也不能随可选音频包一起误删。 |
| [`installer-components.json`](../configs/installer-components.json) 同时定义基础镜像排除项、GNOME 组件和可选功能依赖，[首次启动](../package/custom/openwrt-installer/files/firstboot) 使用 `gnome` 和 `gnome_autostart`。 | 新桌面子包也要排除在基础 squashfs 之外。沿用既有组件 ID、首次启动字段、默认选项和签名离线仓库。GTK/GLib、PipeWire 等按照共享依赖处理，例如 `virt-manager` 使用 GTK，但它的配方已独立于 GNOME。 |

## 包边界

| 包 | 实施后职责与依赖 |
| --- | --- |
| 新增 `openwrt-desktop-base` | 与 `-core` 同配方构建。拥有 `/etc/config/desktop`、PAM、init、`desktop-setup`、`desktop-ctl`、会话调度、VT7 和显卡冷插拔。显式声明公共脚本的运行依赖，例如 `desktop-ctl` 用到的 `python3`。 |
| `openwrt-desktop-core`、`openwrt-desktop-rdp`、`openwrt-desktop` | `-core` 依赖公共包并拥有 GNOME 会话、应用、Portal、Keyring、Mutter 和 GNOME 设置。`-rdp` 继续依赖 `-core` 并拥有 GNOME RDP 配置和预置。完整兼容元包继续选中两者。 |
| `luci-app-desktop`、`openwrt-desktop-audio`、`openwrt-appimage`、`sunshine` | 前三者改依赖 `openwrt-desktop-base`。Sunshine 继续通过音频包取得 PipeWire 等运行环境。 |
| 新增 `openwrt-desktop-ime-base`、`openwrt-flatpak-base` | 在各自现有配方里拆出通用子包。IME 基础包拥有 Fcitx5/Pinyin、CJK 字体和用户配置初始化。GNOME 的 IBus 启动参数、Kimpanel 和会话接线归原 IME 包。Flatpak 基础包拥有运行环境、FUSE、用户工具及通用会话环境导入。原 Flatpak 包组合基础包、GNOME 集成以及原有 GTK Portal 回退。 |

## 实施顺序

1. **建立基线。** 读 `AGENTS.md`、`CLAUDE.md`、[切换器说明](desktop-session-switcher.md)、[验证记录](desktop-session-switcher-validation.md) 和 [APK 发布就绪检查](publication-readiness.md)。记录版本、两类已安装 GNOME 的 APK world 和现有单元关系。保留 `.config`、本地 overlay 和工作树中已有改动。
2. **拆包并迁移会话入口。** 保留 `desktop-setup USER`、`--no-autostart`、GNOME 的 `--refresh-keyring` 和 `desktop-ctl --json`。在现有会话插件上增加可选的凭据初始化、预检与解锁入口。启动、预检和 LuCI 使用同一会话选择规则。显式指定的会话必须可用。未配置时，只在有唯一可用会话的情况下自动选中。零个或多个可用会话时显示明确提示，启动前完成检查。缺少凭据或 RDP 后端时状态显示不适用。继续用 `active.env` 停止旧会话并清理旧环境变量，保留 release 40 对带 systemd drop-in 的 transient unit 重启修复。
3. **移接共享功能。** 公共服务的停止跟随 `graphical-session.target`，启动由会话确认用户总线和实际 Wayland 环境就绪之后触发。把音频、Flatpak 和 Sunshine 的公共启动及 LAN 地址同步移出 GNOME 专用脚本。迁移或兼容读取用户级和系统级已有的 Sunshine 链接，保留单实例、仅监听 LAN、关闭后停止和 LAN 地址恢复后重启的行为。由 GNOME 侧保留 RDP、Mutter 和 Kimpanel 的专用逻辑。保留用户 Fcitx 配置及现有会话的环境清理。LuCI 继续使用同一 RPC、权限及保存后显式重启流程。
4. **收口配置和所有权。** 同步 GNOME 构建配置、安装器排除项和相关包的 release。子包由同一配方产生，同一路径只由一个新包交付。当前打包规则写入 APK `origin`，本机 APK 3.0.5 源码支持同 origin 的文件交接，这是迁移条件之一。必须以实际受保护文件和新旧索引验证 UCI/PAM 交接，禁止用全局 `--force-overwrite` 掩盖冲突。旧 world 如果只有附加包、通过传递依赖装上 GNOME，在升级前显式保留 `openwrt-desktop-core` 或原有完整元包。测试中覆盖该事务。保留原包 ID 所代表的 GNOME 核心、RDP 可选和完整桌面入口。

## 验收与交付

1. **源码与包。** 运行严格 Kconfig 检查及 `git diff --check`，复用 `test-desktop-sessions.py`、`test-luci-desktop.py`、`test-luci-desktop-view.js`、`test-gnome-keyring.py`、`desktop-rdp-config.py`、`test-desktop-audio.py`、`test-desktop-ime.py`、`test-sunshine-gnome.py`、`test-custom-package-updates.py` 和 installer 组件测试。会话测试覆盖无凭据后端、无可用会话、切换前预检和旧会话停止。用完整签名 APK 索引做干净根目录安装，分别核对公共包与全部通用附加包、GNOME 核心、完整 GNOME 和无桌面组合。公共组合不得出现 GNOME Shell、Mutter、GNOME Keyring、GNOME RDP、GNOME Portal 后端、GNOME 应用或 GNOME 兼容元包。记录实际包清单和输入索引。
2. **VM 与客户端。** 以测试会话验证无 GNOME 时的会话管理和 LuCI 状态。用同批 ISO 验证纯路由、GNOME 核心和完整 GNOME。GNOME 测试覆盖冷启动、显卡和本地画面、TPM2 与无 TPM 回退、Pinyin 候选、Portal、PipeWire、LAN 地址变化。用真实 RDP 和 Moonlight 客户端验证画面、键鼠、音频和重连，RDP 同时验证剪贴板。服务 active 或端口监听只是中间结果。测试资源或客户端缺失时记录具体未验收项。
3. **真实滚动升级。** 从已发布旧版 GNOME 核心和完整桌面的实际 APK world 启动 VM，使用完整签名 feed，先模拟再执行且保持包脚本启用。核对 `/etc/config/desktop`、PAM 本地改动、Keyring、TLS、Fcitx、Sunshine 和远程服务状态，以及是否产生需要审查的 `.apk-new`。检查文件归属、会话重启、整机重启和客户端连接。用同一构建重复 `apk upgrade` 只证明当前索引自洽。已有 GNOME 若固化在只读 `/rom`，APK 删除可改变运行根文件系统的视图，清除底层镜像字节需要更换镜像。
4. **交付证据。** 在实现时补充验证记录，列出源码、APK/索引身份、ISO 哈希、VM 与客户端结果及仍待验证项。物理路由器改动和发布分别需要授权。GNOME release 40 的历史实机验证覆盖 LuCI 重启和状态探测，本次新拆包仍需重新完成上述验证。
