# KDE Plasma 6.8.3 移植与实施交接

2026-11-23。规划基线为主树 `978038e643`、独立 video feed `cc362b7`。下文的“现状”取自这份工作树和上游固定标签；“实施”描述待开发功能。本轮交付计划文档，尚无 Plasma APK、安装镜像或运行结果。

## 已定范围与开工顺序

为 x86_64/glibc、原生 systemd 的 OpenWrt 增加普通用户的 Plasma Wayland 会话。沿用 LuCI「服务 → 桌面」、现有 PAM/logind、seat0/VT7 和 systemd 用户总线。用户可以独立安装 KDE，或与 GNOME 共装并切换。整个启动链无需 GDM、SDDM 或 Plasma Login Manager。

| 次序 | 要交付的东西 | 下一步可以据此做什么 |
| --- | --- | --- |
| 1 | Qt 6.11.3、ECM/KF6 6.32.0、Plasma 6.8.3 的库和工作区 APK | 在 target sysroot 编译 KWin、工作区和现有 Qt 应用 |
| 2 | Plasma core、公共凭据助手、会话插件与 LuCI 集成 | **第一个可用里程碑**：从 LuCI 启动 Plasma，看到默认面板，用已安装的 Konsole 开终端 |
| 3 | 日用元包、系统设置、Dolphin、声音、拼音和 KDE Portal | 日常本地使用，同一账号可切回 GNOME |
| 4 | KDE 的 LAN KRdp、RDPSND 播放和 Sunshine 集成 | 两种客户端均能操控当前本地桌面并播放桌面声音 |
| 5 | 离线安装组件、TUI、应答文件与 firstboot | 从同批 ISO 安装纯 Plasma，或在现有系统上追加 APK |

优先把第 1、2 步做通。可以用已有 GNOME VM 追加包调通会话，不必在依赖移植期间反复生成 ISO。将远程音频作为独立改动维护；其完成时间不会阻塞本地桌面的开发。首版验收见文末。

## 1. Qt、Frameworks 和 Plasma 的包边界

**现状。** video feed 的 Qt 公共版本在 [qt6/common.mk](../feeds/video/frameworks/qt6/common.mk)。主树还有独立固定 6.9.3 的 [qt6wayland 配方](../package/custom/qt6wayland/Makefile)、Multimedia、Speech 等模块。工作树中有 34 个 `package/custom/kf6-*` 目录、ECM 6.20.0、Konsole 26.08.3，以及可复用的 [KF6 交叉编译和 staging 规则](../include/kf6-package.mk)。现有 Qt/KF6 足以运行 Konsole，KWin 6.8.3 则要求 Qt ≥ 6.11、KF6 ≥ 6.30 和 C++23。[KWin 构建定义](https://github.com/KDE/kwin/blob/v6.8.3/CMakeLists.txt)

1. 将 video feed 的 Qt Base、Declarative/Quick、ShaderTools、SVG、Tools、Translations 与主树 Qt 模块统一到 6.11.3，逐项换源码哈希，重审本地补丁及该系列适用的官方修复。先构建 host 工具，再通过 `QT_HOST_PATH` 给 target 交叉编译使用。重点对齐 moc、rcc、QML cache/type registrar、Wayland scanner、GuiPrivate 和 QML 私有接口。重建引用 Qt 私有 ABI、QML 插件或旧 Qt 构建工具的消费者。[Qt 发行目录](https://download.qt.io/archive/qt/6.11/)
2. **解决 Qt Wayland 文件交接。** 当前配方从 qtwayland 的安装目录复制平台插件和客户端库，单独提供 host scanner，并显式关闭 compositor 构建。Qt 6.11 的 qtbase 已构建 Wayland 平台插件。以两个新模块的实际 install manifest 列出 `.so`、插件、scanner、头文件和 CMake targets，给每个路径指定唯一 APK owner；保留 `qt6waylandclient` 和 `qt6waylandclient-dev` 的依赖入口。调整生产这些包的配方和旧版升级的替换关系，避免两个配方同时定义相同包名或安装相同文件。保留 Wayland、xcb、EGL、xkbcommon；按消费者声明实际需要的 Wayland 开发组件。[Qt 6.11.3 平台插件目录](https://github.com/qt/qtbase/blob/v6.11.3/src/plugins/platforms/CMakeLists.txt)
3. 将 ECM 和已用 KF6 配方整组更新至 6.32.0。用固定标签的 `find_package`、`pkg_check_modules` 和 QML import 列表补齐缺项，优先处理 Qt Core5Compat、KAuth、KIdleTime、KSvg、KRunner 等。现有 KIO 显式设置 `WITH_WAYLAND=OFF`，KWindowSystem 设置 `KWINDOWSYSTEM_QML=OFF`，逐项对照 Plasma 消费者。保留 Konsole 所需的 Kirigami、KCoreAddons、KCMUtils QML 插件。原有“Get New…”对话框的 QML 探针可快速定位“Qt 程序能打开但局部页面空白”。[KF6 发行目录](https://download.kde.org/stable/frameworks/6.32/) · [现有 Konsole 验证记录](konsole-validation.md)
4. 建立 Plasma 依赖顺序。先 staging KDecoration、KScreenLocker、KGlobalAccelD、KPipeWire、Plasma Activities、libplasma 等组件的开发文件，再构建 KWin、plasma-workspace、plasma-desktop 和 Breeze，随后接入 xdg-desktop-portal-kde、KScreen、System Settings、Dolphin。每个上游源码包维护单独配方；具体编译边由固定标签声明，清单中的顺序用于组织工作。KWin 要求 Vulkan、Wayland 1.26、Wayland Protocols 1.49、libinput ≥ 1.28、libdrm ≥ 2.4.127 等，当前树已有 Wayland 1.26.0、Wayland Protocols 1.49、Plasma Wayland Protocols 1.23.0、libdrm 2.4.133。先核对 staging，避免重复移植。
5. 打包 Qt 插件和 QML import 的同时，保留 Plasma 的 KCM、默认面板 containment、主题、D-Bus service、systemd user unit、翻译和 Wayland 会话资源。桌面只提供 Wayland 会话，保留 Xwayland 兼容应用。避免把 SDDM 主题/KCM、登录管理器守护进程、display-manager.service 或 plasma-nm 引入产品依赖。netifd/UCI 继续管理路由网络。

| 用户安装入口（待新增） | 文件或依赖所有权 |
| --- | --- |
| `openwrt-desktop-plasma-core` | 依赖公共 desktop base、共享密钥环助手、KWin、工作区、Breeze、KScreenLocker、Polkit agent、KDE Portal；安装会话插件和 Plasma 专用集成文件 |
| `openwrt-desktop-plasma` | 日用元包，拉入 core、System Settings、KScreen、Dolphin、现有 Konsole、桌面音频和 Plasma 拼音集成。直接 APK 安装入口 |
| `openwrt-desktop-plasma-rdp` | 依赖 Plasma core、KRdp 和播放所需音频组件；安装后端凭据助手和 Plasma 的 LAN RDP 用户服务集成 |
| `luci-app-desktop`、`sunshine` | 沿用现有包。安装器的桌面选项带上 LuCI；Sunshine 保持独立可选 |

新增 Plasma 配置片段，区分构建可选 APK 与在镜像根中预装桌面。保留现有工作 `.config`，参考 [本地构建指南](local-build.md) 合并配置。每个新增 custom 配方登记到 [更新清单](../configs/custom-package-updates.json)。Qt 升级包含独立 video feed 的改动，分别维护该 feed 的提交与主树镜像补丁/manifest。改动已发布的同版本包内容时递增包 release。

## 2. 接入现有 VT7 和 LuCI 控制链

**现状。** [desktop.init](../package/custom/openwrt-desktop/files/desktop.init) 先解析 UCI、用户和会话，再通过 `systemd-run --uid=… --property=PAMName=openwrt-desktop` 创建临时系统服务。有 VT 时切到 tty7；[desktop-session](../package/custom/openwrt-desktop/files/desktop-session) 在 PAM 创建的 runtime dir 中连接已有用户总线，清理桌面环境变量、解锁凭据并调用插件。停止流程读取 `/run/openwrt-desktop/active.env` 中的原用户和会话。显式停止还设置 `manual-stop`，避免 DRM 热插拔又把桌面拉起。复用这条链即可。[会话接口](desktop-session-switcher.md) · [公共包拆分及 VM 记录](desktop-package-decoupling-validation.md)

**实现插件。** 参照 [GNOME 插件](../package/custom/openwrt-desktop/files/sessions.d/gnome)，安装 root 所有、模式 0644 的常规文件 `/usr/libexec/openwrt-desktop/sessions.d/plasma`。关键元数据保持逐行静态赋值，让 LuCI 发现阶段能够直接解析：

```sh
SESSION_ID="plasma"
SESSION_TITLE="KDE Plasma (Wayland)"
SESSION_DESCRIPTION="KDE Plasma 6.8 Wayland desktop with KWin"
SESSION_EXEC="/usr/bin/startplasma-wayland"
SESSION_SUPPORTS_RDP="1"
SESSION_SUPPORTS_KMS_SCHEDULING="0"
SESSION_CREDENTIAL_BACKEND="gnome-keyring"
SESSION_RDP_UNIT="app-org.kde.krdpserver.service"
SESSION_UNSET_VARS="KDE_FULL_SESSION KDE_SESSION_VERSION KDE_SESSION_UID"
```

| 钩子 | 实现要点 |
| --- | --- |
| `desktop_session_check` | 只读检查 startplasma、KWin、plasmashell 和 Plasma Wayland target 是否可用。此时 KWin 尚未取得 seat，故不检查显示 socket 是否存在 |
| `desktop_session_setup`、`desktop_session_user_setup` | 配置公共凭据和 TLS，幂等初始化本用户的 Plasma 默认设置。可选输入法、远程后端只在相应包安装后配置 |
| `desktop_session_credential_prop`、`desktop_session_unlock` | 提取 GNOME 插件已有的文件合法性、所有者与权限检查，复用 `LoadCredentialEncrypted` / `LoadCredential` 和现有解锁助手 |
| `desktop_session_exec` | 设置 `XDG_CURRENT_DESKTOP=KDE`、`XDG_SESSION_DESKTOP=KDE`、`XDG_SESSION_TYPE=wayland`、`DESKTOP_SESSION=plasma` 和应用导出目录，导入用户管理器，最后 `exec /usr/bin/startplasma-wayland`。由上游 workspace target 启动 KWin 和 plasmashell |
| `desktop_session_stop` | 对当前用户总线调用 `org.kde.Shutdown.logout`，有界等待工作区退出、远程监听释放，再交回公共 stop 流程。保留同用户 SSH、user manager 和其他 logind 会话 |

上游会话文件使用“必要时创建总线”的 wrapper；在本树中用户总线已由 PAM/systemd 提供。上游 `plasma-workspace-wayland.target` 绑定 KWin，`plasma-workspace.target` 与 `graphical-session.target` 相连。避免在系统启动脚本里单独拉起第二个 KWin 或 dbus-daemon。[会话入口](https://github.com/KDE/plasma-workspace/blob/v6.8.3/login-sessions/plasmawayland.desktop.cmake) · [Wayland target](https://github.com/KDE/plasma-workspace/blob/v6.8.3/startkde/systemd/plasma-workspace-wayland.target) · [退出接口](https://github.com/KDE/plasma-workspace/blob/v6.8.3/startkde/plasma-shutdown/org.kde.Shutdown.xml)

**切换与状态。**

1. 在 [desktop-ctl](../package/custom/openwrt-desktop/files/desktop-ctl) 对照 `parse_session_plugin`、`preflight_start`、`do_switch`。现在发现阶段主要检查 `SESSION_EXEC`，而 init 的 shell 解析器会调用真正的插件检查；`do_switch` 会先写 UCI，再 restart。在执行切换前用同一个受信插件检查入口预检目标，沿用现有 ID 校验、root 文件校验和只读状态解析。检查失败时直接返回缺项，原桌面和选择均保留。运行时启动失败应带回实际状态和错误，方便从原页面切回已安装会话。
2. 进程环境清理和 `systemctl --user unset-environment` 都要覆盖旧 `DISPLAY`、`WAYLAND_DISPLAY`、KDE/Mutter、Qt 输入法等变量。新显示名由新 compositor 发布。已驻留的 Portal 后端须随对应图形会话结束，以免双桌面来回切换后 KDE 请求仍落到 GNOME。
3. `active.env` 在临时服务启动后即写入，适合识别停止对象。对 Plasma 的“就绪”另看用户总线上的 KWin、plasmashell 及有效 Wayland socket。在 LuCI 轮询展示“启动中/就绪/失败”，无需把桌面完整启动时间塞进同步 RPC。保存并应用沿用现有的漂移提示，切换并重启才执行切换；RDP 状态按活动会话的 `SESSION_RDP_UNIT` 查询，Mutter 调度项按能力隐藏。变更点集中于 [LuCI 视图](../package/custom/luci-app-desktop/htdocs/luci-static/resources/view/desktop/settings.js)，沿用现有读写 ACL。
4. `/etc/config/desktop` 的实际默认 `session` 为空。单个可用会话自动选择，多个则需显式配置；现有 `desktop-setup` 通常已经固定所选会话。升级时尊重已有值。对已配用户且仍依靠空值运行 GNOME 的旧系统，追加第二桌面前依据当前活动会话或原来唯一可用的会话固定选择。APK 安装阶段不重启桌面，也不对离线镜像运行 live user setup。

## 3. 日用集成，哪些现成组件可以直接用

- **共享凭据。** 当前 `desktop-keyring-unlock`、`desktop-keyring-control-unlock`、`desktop-gnome-keyring-setup` 归 GNOME core 所有，而公共 base 本身没有 GNOME 依赖。将这些助手连同所需依赖提取为两个 core 共用的凭据子包，保留旧脚本入口、`/etc/desktop/gnome/<uid>.keyring-passphrase[.cred]` 和现有 TLS 路径。滚动升级处理文件所有权交接。复用 TPM2 SRK 密封与无 TPM 的既有回退；KDE 下让 QtKeychain 的读写都选择同一个 Secret Service，避免 KWallet 争用 `org.freedesktop.secrets`。锁屏另给 KScreenLocker 安装普通用户密码认证的 `kde` PAM 配置；公共启动使用的 `pam_rootok` 栈不能拿来解锁屏幕。[现有包归属](../package/custom/openwrt-desktop/Makefile) · [KScreenLocker 的 PAM 选择](https://github.com/KDE/kscreenlocker/blob/v6.8.3/CMakeLists.txt)
- **中文输入。** `openwrt-desktop-ime-base` 已提供词库、字体和 `desktop-ime-init`；后者只在文件缺失时安装默认拼音配置。GNOME 的 `openwrt-fcitx5.service` 有 `PartOf=gnome-session.target`，并通过 `--enable=ibusfrontend` 和 Kimpanel 集成。Plasma 复用 base、加上 `fcitx5-qt`，用 KWin 的 Wayland 输入法设置选中 Fcitx5 启动项，避免同一账号出现两个前台进程。默认值只初始化一次，用户已有输入法选择优先。[IME 配方及文件](../package/custom/openwrt-desktop-ime/)
- **音频、Flatpak、Portal。** 公共 `openwrt-desktop-services.service` 已挂到 `graphical-session.target`，在 Wayland 环境就绪后调用音频与 Flatpak 助手并管理 Sunshine。早期 switcher 文档里“将共享服务迁出 GNOME target”的建议已有部分实现，先读现行代码。KDE 使用 `xdg-desktop-portal-kde` 和桌面专属选择配置，文件选择、ScreenCast、RemoteDesktop 走 KDE 后端。若选择 Flatpak，KDE 装 `openwrt-flatpak-base`；原 `openwrt-flatpak` 包会拉入 GNOME core 和 GNOME Portal。[公共服务](../package/custom/openwrt-desktop/files/desktop-session-services) · [Flatpak 包拆分](../package/custom/openwrt-flatpak/Makefile)
- **显示与电源。** 沿用 GPU coldplug、VT 和普通用户设备权限。没有 KDE 已保存布局且 LuCI 有明确输出或模式时，用 KScreen 在首次启动后应用初始首选值。遇到多屏或不支持的模式，保留 KWin 可用布局，交给系统设置调整。保留 Breeze 默认布局、桌面锁屏和 Polkit，默认电源策略避免空闲时挂起整台路由器。

## 4. KRdp、客户端音频和 Sunshine

**先做 KRdp 视频、输入及凭据。** 固定 KRdp 6.8.3。上游要求 Qt6GuiPrivate、FreeRDP/WinPR/server、Qt6Keychain、KPipeWire、PAM 和 libei ≥ 1.6；本树已有 FreeRDP 3.33.1、libei 1.6.0、PipeWire 1.6.11。上游直接执行 `add_subdirectory(server)`，`BUILD_EXAMPLES` 仅控制 examples 目录，可在目标配方中关闭。将 `krdpserver`、所需编码器及用户单元收入实际运行包；启用与现有硬件和 VM 软件编码均适配的 H.264 路径。[KRdp 构建定义](https://github.com/KDE/krdp/blob/v6.8.3/CMakeLists.txt)

1. 把 `desktop-rdp-setup USER [--password-stdin]` 从 GNOME RDP 包移入共享 RDP 子包，给它增加 `--session gnome|plasma`。默认选活动会话，停止时选已配置会话。GNOME 继续调用原来的 grdctl 助手；Plasma 助手以桌面用户身份设置允许的用户名、TLS 文件和端口，使用 QtKeychain 向服务名 `KRDP`、键名为用户名的条目写密码。沿用终端隐藏输入/stdin，避免进程参数、UCI、日志或 LuCI 输出明文。完成持久化后才启用该后端。保留两套后端各自的凭据条目。[现有 GNOME 配置助手](../package/custom/openwrt-desktop/files/desktop-rdp-configure) · [KRdp 读取凭据及参数](https://github.com/KDE/krdp/blob/v6.8.3/server/main.cpp)
2. 上游 `app-org.kde.krdpserver.service` 直接启动二进制，默认监听地址为通配地址。为其安装 OpenWrt drop-in，把 ExecStart 指向本地 wrapper，复用 root 写入的 `/run/openwrt-desktop/<uid>.env`。仅在当前 Plasma 会话、已配置凭据、RDP 已开启且 LAN IPv4 有效时，传入明确的 `--address`、`--port`、TLS 参数及 `--mode SharedAccess` 启动。Plasma 管理助手跟随 LAN 状态启停及重绑，退出时先释放监听，让下一个桌面可接管相同端口。无论上游 KCM 还是 LuCI 发起启动，最终都经过同一 wrapper。按 KRdp 应用身份配置 KDE RemoteDesktop Portal 授权。[上游用户单元](https://github.com/KDE/krdp/blob/v6.8.3/server/app-org.kde.krdpserver.service.in) · [现有 LAN 状态生产者](../package/custom/openwrt-desktop/files/desktop.init)
3. **独立实现 RDPSND。** KRdp 标签源码的 `RdpConnection.cpp` 已有 CLIPRDR 和视频连接逻辑，并显式将 `FreeRDP_AudioPlayback` 设置为 false；启用 PipeWire 或单改布尔值都无法传音频。按每条通过认证的 peer 创建 FreeRDP `RdpsndServerContext`，在客户端加入声音通道时初始化、发布支持格式、选择双方格式。首版实现 48 kHz、双声道、16 位 PCM。格式协商后开始读取 PipeWire 默认输出的 monitor；客户端不请求声音或协商失败时继续画面和输入。[KRdp 连接实现](https://github.com/KDE/krdp/blob/v6.8.3/src/RdpConnection.cpp) · [FreeRDP 3.33.1 RDPSND 接口](https://github.com/FreeRDP/FreeRDP/blob/3.33.1/include/freerdp/server/rdpsnd.h)
4. 将采集和发送解耦。PipeWire 回调只提交完整 PCM 帧到有界队列，发送端按帧数调用 `SendSamples`，积压时淘汰过期帧。设备切换时重新选择默认输出；断开时先停止输入和排队，等待回调退出，再回收 context。遵守 KRdp 的 peer 线程和 teardown 所有权，避免从 PipeWire 回调关闭或操作 transport。本树的 FreeRDP 已开 server channels，ALSA/Pulse 后端关闭不妨碍服务端从 PipeWire 取样。现有 GNOME 音频修复可用于理解“固定设备延迟”和“队列增长”的区别，长时间延迟回归留到需要时。[现有 FreeRDP 配方](../package/custom/freerdp/Makefile) · [GNOME 音频修复](../package/custom/gnome-remote-desktop/patches/005-ignore-constant-audio-device-latency.patch)
5. **Sunshine。** 继续使用 `sunshine-setup USER --capture=portal` 做用户和虚拟输入授权，复用配对信息、音频和现有 LAN 绑定。Plasma 配置 KDE ScreenCast Portal，首次授权后用 Moonlight 连接当前桌面。已有显式 KMS 选择和 Intel 设备专用编码器规避逻辑继续交给现有 wrapper。在切换后重新获得当前显示和音频。[Sunshine 启动助手](../package/custom/sunshine/files/sunshine-session)

## 5. 离线安装器和首启数据流

当前 [组件目录](../configs/installer-components.json) 和组件 catalog 均采用 format 2。只修改 TUI 标签不足以增加 KDE，介质构建器和目标端都会自行计算包列表。按以下路径贯通一次：

1. **目录和解算。** 新增默认未选的 `plasma`，携带 core、System Settings、KScreen、Dolphin、Konsole、LuCI。离线安装仍允许单独勾选音频、IME、RDP、Sunshine。将附加组件的 `depends: ["gnome"]` 改为“至少选中 GNOME 或 Plasma”；保留 Sunshine 对 audio 的普通必选依赖，KDE RDP 选中时拉入声音所需组件。复用 `conditional_packages.when_all` 为 GNOME/KDE 各加后端，共装时去重。Flatpak、AppImage 及 virtualization 中按桌面安装 virt-manager 的现有条件也要检查。
2. **保证介质和安装目标解释一致。** 同步更新 [介质构建与离线索引](../scripts/build-installer-components.py)、[目标组件解析](../package/custom/openwrt-installer/files/core.py) 和 [catalog 加载/事务预演](../package/custom/openwrt-installer/files/apply.py)。新引入的“任一桌面”条件要序列化到介质 catalog，旧 catalog 缺字段时沿用原语义。如为新语义提升 catalog 版本，读取端保留旧 format 2 并区分外层 payload 版本。将 GNOME 的 `forbidden_when_unselected` 里共享 base 移出，分别约束纯路由基础包、桌面专属包和可共享依赖，以免纯 KDE 被构建器误判。更新构建脚本内写死的代表性选择。
3. **界面和无人值守。** [TUI](../package/custom/openwrt-installer/files/tui.py) 的 accounts 当前接收 `has_gnome`，输出 `gnome_autostart`。改为按所选桌面生成 `desktop_session`、`desktop_autostart`。单选时自动确定、双选时让用户明确选择，纯路由跳过。core 校验及摘要使用相同字段；兼容旧应答文件的 GNOME 设置和无组件 catalog 的老安装路径。
4. **firstboot。** apply 将普通用户、组件、所选会话和自启设置写入原有私有 firstboot 文件。[firstboot](../package/custom/openwrt-installer/files/firstboot) 创建或复用用户后，先写入 `desktop.main.session`，再按自启选择执行 `desktop-setup USER` 或 `desktop-setup USER --no-autostart`，按组件执行音频等设置。双桌面用户的专用助手要能在首次切入相应桌面时完成幂等初始化。当前 `desktop-setup` 默认会启用并重启服务，因此不应把它当作普通 APK 安装钩子。全流程成功后才删除 firstboot 文件，失败保留以便重试。

## 首版验证与接手入口

**一台一次性 VM，三步。** 构建时运行直接涉及的现有测试。首版不要求安装组合矩阵、长时间串流或实机性能报告。

1. 用同批签名离线索引和 ISO 安装 Plasma、日用附加项和两种远程服务。进入桌面、打开 Konsole，输入中文并播放声音。
2. 在同一 VM 追加 GNOME，从实际 LuCI 页面完成一次 Plasma → GNOME → Plasma，看到两个桌面，键鼠可用。
3. FreeRDP/Remmina 与 Moonlight 各连一次，均能看到并操作本地桌面、听到测试音；RDP 顺手复制一段中文并反向粘贴。记录实际客户端和结果。TLS/NLA 成功、端口监听和 user unit active 只能帮助定位连接阶段。

局部改动优先使用已有测试入口：

```sh
python3 scripts/tests/test-desktop-sessions.py
python3 scripts/tests/test-luci-desktop.py
node scripts/tests/test-luci-desktop-view.js
python3 scripts/tests/test-installer-components.py
python3 scripts/tests/test-custom-package-updates.py
```

**定位失败时的第一站。** LuCI 看不到会话，先查插件文件、owner、静态元数据和 `desktop-ctl --json status`；会话反复退出，查 `journalctl -b -u openwrt-desktop.service`，再在桌面用户的总线上看 `plasma-workspace-wayland.target`、`plasma-kwin_wayland.service` 和 plasmashell。只有背景没有面板，先查 workspace 默认布局和 QML import。RDP 能登录但无声音，依次查客户端声音重定向、RDPSND 协商、PipeWire monitor 选取和发送帧数。纯 KDE 安装被判定拉入禁包，先对照 catalog 的条件、共享包 owner 和构建端/目标端两套解算。

已有验证可以缩小排查范围。公共 desktop base 加 dummy 会话已经在 VM 中走通过 PAM、VT7 和 LuCI 启停；已有 GNOME 物理记录对应较早的桌面包版本，不能证明 Plasma 可用。下一位实施者从 Qt/KF6 的包归属和 staging 开始，完成各阶段后另记真实构建/运行证据。LAN feed 发布、物理设备安装和桌面重启分别授权。[会话切换记录](desktop-session-switcher-validation.md) · [包拆分记录](desktop-package-decoupling-validation.md) · [安装器实施记录](installer-components-implementation-validation.md)
