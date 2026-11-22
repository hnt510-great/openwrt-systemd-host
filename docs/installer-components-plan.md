# 安装器可选组件：远期计划与源码调查

**远期计划。组件安装尚未实现，执行时间待定。**

初稿为 2026-11-16，2026-11-19 按 `a5650a322c` 更新。纯路由配置已独立构建并
通过网络和恢复 VM 验证，GNOME 与 Flatpak、virt-manager 与 GNOME 的包依赖
已解耦。现有安装器仍通过 `TARGET_DIR_ORIG` 生成一份完整 squashfs，供 live
启动和目标安装共用。独立基础层、签名离线仓库、组件选择、按组件首次初始化
和新安装组合的滚动升级验收仍待实施。

现有安装流程见 [安装器指南](installer-iso.md)，构建和已有验收见
[实施进度与验证记录](installer-components-implementation-validation.md)。

## 1. 已与用户确认的目标

用户希望系统功能可以在安装时选择，并强调不要过度设计。讨论已确认：

- **真正选择安装组件**：未选功能的软件不安装，不只是保留完整镜像后关闭服务。
- 首版覆盖常用桌面组件，并加入虚拟化和容器。
- 安装后先继续使用 APK 管理，不新增统一组件管理菜单或 LuCI 页面。
- 基础系统保留现有路由与运维功能，包括代理、文件共享、监控等既有范围，
  不趁此改成只有基础联网功能的精简发行版。
- 功能选择页默认全部勾选，用户取消不需要的组件。

实现方案沿用现有 GNOME。保持 BIOS/UEFI、USB/光盘、整盘 GPT、
ext4/btrfs/xfs overlay 和后续 kernelctl/APK 升级方式。正常 combined 镜像继续
沿用自己的构建路径和本地 overlay。

x86/64 按 [systemd 单 init 基线](systemd-only-plan.md) 运行。安装器和已安装系统
正常引导均以 systemd 为 PID 1，保留 OpenWrt preinit、原生 `failsafe=true`
控制台及 systemd 托管的 procd API。整机换盘使用安装介质或离线磁盘镜像。

## 2. 计划中的组件与行为

| 组件 | 内容 | 组件级依赖 |
| --- | --- | --- |
| GNOME 桌面 | 当前 GNOME 桌面及桌面应用，包括现有浏览器 | 基础系统 |
| Audio | 桌面播放、录音及音频集成 | GNOME |
| 中文输入法 | Fcitx5、拼音、相关字体和桌面集成 | GNOME |
| RDP | GNOME 远程桌面 | GNOME |
| Sunshine | Moonlight 串流 | GNOME、Audio |
| Flatpak | 当前 Flatpak 集成 | GNOME |
| AppImage | 当前 AppImage 支持 | GNOME |
| 虚拟化 | QEMU、libvirt、固件、命令行和现有 LuCI 管理 | 不依赖 GNOME；同时选 GNOME 时安装 virt-manager |
| 容器 | Podman、rootless 支持及现有 LuCI 管理 | 不依赖 GNOME |

组件依赖用于界面解释和校验，包依赖仍交给 APK。缺少组件依赖时在选择页提示，
保留用户选择，允许修改；不默默把用户取消的组件重新勾上。

“安装组件”不等于自动开放远程访问或授予管理权限。GNOME 自启沿用现有账户选项；
RDP 凭据、Sunshine 配对、rootless 用户登记以及虚拟机管理授权继续使用现有工具。
不自动下载 Flatpak 应用、容器镜像，不创建虚拟机或容器。

内核及所选驱动继续使用同一构建的完整内核包，首版只拆用户态功能。
公共依赖可因其他组件需要而保留；例如取消 Audio，不应删除 GNOME 录屏、
屏幕共享所需的 PipeWire 服务或库。Audio 代表音频集成这一组，不能承诺
“系统中不存在任何音频相关库”。不新增独立的无桌面音频方案。

## 3. 实施方案

### 构建与 ISO

1. 新增一份 `configs/installer-components.json`，集中维护基础保留包、各组件的
   顶层包、组件依赖和默认选择。对照当前完整配置，逐项归组桌面应用、容器工具、
   虚拟化/容器的 LuCI 应用与翻译包，避免组件取消后又通过其他顶层包被带回。
   [纯路由配置](../configs/x86-64-systemd-router.config) 可用于核对基础网络包。
   该配置关闭了安装器，也省去了 Passwall、SmartDNS、Samba 和 `router-audit`。
   安装器基础层应按当前完整配置明确保留这些既有运维功能及 LuCI 集成，并核对
   签名 feed 同步、APK 事务恢复和 kernelctl 的顶层包与依赖。
2. 从同次构建的 APK，在独立目录组装基础 rootfs，不再把完整桌面 rootfs 作为
   安装器 squashfs。沿用共享的 live squashfs/基础安装载荷思路；其中须保留
   安装器运行、分区、文件系统格式化和离线安装必需的工具。参考
   [安装器配置片段](../configs/installer-iso.config) 及现有安装器包依赖。
3. ISO 携带基础 squashfs、组件清单和签名离线 APK 仓库。USB 和光盘均可复用
   现有只读 ISO9660 的 `/install` 内容入口，继续由 APK 求解依赖闭包。
4. 只使用同次构建、版本和 ABI 一致的内核、基础系统、索引和软件包；携带公钥，
   不携带私钥。基础系统、仓库和清单的身份要能在预检时核对。
   2026-11-19 隔离验证的纯路由镜像使用 `7.3.5-1-openwrt`，完整桌面构建使用
   `7.3.5-70-openwrt`，两者 ABI 不同。新增的 GNOME 构建片段还会修改内核
   抢占选项。组件清单只表达用户态 APK 请求，所有选择共用支持完整组件集的
   内核及所选驱动。
5. 保留现有“干净镜像”边界：仅带受 Git 跟踪的 `files/` 默认值，排除个人账号、
   代理节点、密钥和未跟踪 overlay。不覆盖当前工作 `.config` 来制作精简系统。

基础包名单不能简单采用当前所有 `CONFIG_PACKAGE_*=y`：它混有用户选择和依赖，
会把要拆出的功能继续固化到基础层。需要明确维护顶层包归属，再由 APK 补齐
基础系统需要的公共依赖。验收必须同时检查只读层与目标系统 APK 清单。

### 安装器与接口

- 新增功能勾选页，返回时保留已选状态。
- `--answers` 增加 `components` 列表：空列表为仅基础系统，省略为全选；
  拒绝未知组件和不合法的组合。该默认值保留既有无人值守调用的完整功能意图。
- 摘要及 `--dry-run` 显示最终组件、包数量和空间需求。
- 擦盘前完成离线依赖求解、签名/包完整性、版本一致性和空间检查；缺包或损坏
  必须在破坏性操作之前失败。不得临时联网补齐，以免依赖生产 feed 的即时状态。
- overlay 保留原最小容量要求，并且能够容纳所选包的解压占用及至少 1 GiB
  预留空间。须计入安装与缓存生成的实际开销，不能只按 APK 压缩大小估算。
- 基础 squashfs 写入并验证后，在目标 squashfs 与持久 overlay 合并后的根目录
  中安装所选 APK。
  安装脚本、用户组、alternatives 和启动链接按离线安装语义处理；不得意外
  启动 live 系统中的服务。全部步骤成功后才显示安装完成。
- 首次启动完成所需账户、桌面及音频初始化；将桌面初始化与是否自启分开，
  使自启关闭时也能保留正确的组件配置。失败保留请求和日志，支持现有重试机制。

这不是对旧 ISO 格式兼容性的承诺。实施时需给新载荷明确的格式标识，遇到
不支持的载荷应在擦盘前报错；保留已有 ISO，不原地改写已验证产物。

### 组件包依赖

- **RDP 待拆分。** `openwrt-desktop` 仍强制依赖 `gnome-remote-desktop`，并提供
  RDP setup、用户服务配置和 drop-in。拆分时核对这些入口及包归属，确保无 RDP
  的 GNOME 会话正常，并保留完整桌面中的 RDP 功能和滚动升级兼容性。
- **Flatpak 已解耦。** `xdg-desktop-portal` 保留 `bubblewrap` 沙箱，在构建期
  生成 Flatpak 接口。选择 Flatpak 时由 `openwrt-flatpak` 引入运行时。
  仍需验证不带 Flatpak 的 GNOME 门户，以及安装 Flatpak 后的应用和门户功能。
- GNOME Shell 直接依赖 `pipewire`、`libpulse`；Mutter、门户及 RDP 还依赖
  `libpipewire`。不应把取消 Audio 实现为删除或全局屏蔽 PipeWire。
- `sunshine` 依赖 `openwrt-desktop-audio`；后者依赖 `openwrt-desktop`。
  当前 Audio/IME/Flatpak/AppImage 集成均围绕桌面设计。
- **virt-manager 已解耦。** 仍依赖 `libvirt-daemon`，已移除对
  `openwrt-desktop` 和 `desktop-common.sh` 的依赖。无桌面虚拟化的顶层包可参考
  [无头虚拟化片段](../configs/virt-headless.config)，图形前端按第 2 节的选择规则加入。
- 容器顶层包可参考 [Podman 片段](../configs/podman.config)。
  `openwrt-podman-rootless` 可用于无桌面组合，用户登记仍需显式执行。

Flatpak 和 virt-manager 的解耦已通过严格 Kconfig、隔离包构建和 APK 依赖核对。
待验证的应用运行场景见 [解耦验证记录](systemd-router-decoupling-validation.md#范围与未验证边界)。

### 实施顺序

1. 先在隔离目录从同次构建的 APK 组装基础层和签名仓库。用现有安装路径和临时
   目标根验证擦盘前的离线预检、合并根上的 APK 事务、目标数据库与 world，
   以及安装后可用的生产 feed 配置。并行核对 RDP 拆分后的两种桌面依赖闭包。
2. 接入组件选择、`--answers`、安装摘要和首次初始化，再运行第 6 节的组合
   安装与滚动升级验收。

## 4. 以后接手时的源码入口与注意事项

| 入口 | 当前作用与复用点 |
| --- | --- |
| `target/linux/x86/image/Makefile` 的 `Build/installer-iso` | 目前复制 `TARGET_DIR_ORIG`，加入受跟踪默认值，生成 squashfs、光盘 bootstrap 和 ISO；组件化需在这里改变基础 rootfs 来源 |
| `scripts/build-installer-iso.py` | 混合 BIOS/UEFI ISO、启动文件、manifest 和单份追加 squashfs 的组装入口 |
| `scripts/build-installer-initramfs.py`、安装器 `live-init` | USB p3 或只读光盘 loop 启动；精简 live root 时仍要保证冻结工具、动态加载器及其库齐全 |
| `package/custom/openwrt-installer/files/core.py` | 纯规划、校验、分区、UCI 序列化及脱敏摘要 |
| 同目录 `apply.py` | 来源识别、写前准备、源/目标哈希检查、实际写盘、挂载与清理 |
| 同目录 `tui.py`、`firstboot` | 页面、状态导航、安装进度及安装后账户/桌面初始化 |
| `package/Makefile` 的 `apk_install_rootfs` | 使用 host APK、签名索引、`--no-scripts` 和独立 root 组装软件的现成模式 |
| `include/rootfs.mk` 的 `prepare_rootfs` | 离线 post-install、alternatives、初始化脚本启用等现有语义；不能直接整段搬到运行中的目标挂载树 |
| `include/image.mk` 的 `target-dir-%` | 独立 rootfs 变体的先例，不能据此直接认为删除几个元包就能得到干净基础层 |
| 各 `openwrt-desktop*`、`openwrt-flatpak`、`openwrt-appimage`、`sunshine` 配方和 setup 工具 | 已有功能分组与配置入口，优先复用，避免再造配置框架 |

特别注意：

- `prepare_rootfs` 除 post-install 外，还清理 `/boot`、临时文件等并批量启用
  init 脚本。运行时安装只应复用需要的语义，不能照搬整个宏。
- 当前 `prepare_rootfs` 会从 APK 脚本归档执行并移除 post-install；后续在目标
  overlay 新增 APK 后，不能只解包文件而漏掉相应的离线初始化。
- 本机 APK 3.0.5 源码的选项名是 `--force-no-chroot`，不是
  `--no-chroot-scripts`；有 `--preserve-env`。源码入口为 `apk_db_run_script()`。
  这些选项的存在不代表对本项目所有包脚本都安全：实施前应核对
  `IPKG_INSTROOT`、脚本环境、目标路径和实际副作用，再确定运行方式。
- 当前 firstboot 只读取普通用户请求，创建账号、设置密码，并在自启启用时调用
  `desktop-setup`。它还没有按组件初始化 Audio、容器或虚拟化的完整逻辑。
- 普通用户主目录下的服务链接、设备权限和 UCI 状态也会影响功能行为，不能仅
  检查包是否安装。`desktop-user-setup`、`desktop-gnome-remotes` 和各 setup
  脚本是相关入口。已有配置是可复用基础，不是现成的统一功能管理器。

### Rolling 升级兼容约束（实施验收条件）

- 组件选择只决定新安装系统的顶层 APK 请求，不重写现有设备的 world，
  不根据安装器默认全选给已有设备补装组件。
- 新系统必须保留完整 APK 数据库、签名公钥、生产 feed 同步、事务恢复、
  kernelctl 和内核元包。离线安装的路径和精确版本约束不得永久锁死后续升级。
  目标安装必须在合并根目录进行，不能只向 upper 解包而漏掉包数据库。
- RDP 依赖拆分时，用旧完整系统的 world 和已安装包对新包求解升级，覆盖 RDP 原先
  仅由桌面包依赖引入的情况，验证既有 RDP 包、凭据、用户服务和 UCI 配置保留。
  同时验证已安装 Flatpak 的门户接口。共享包变化需覆盖普通 combined 镜像与
  既有设备的升级路径。
- 保留内核首次接管、版本化内核并行安装、启动计数、确认、回退与 rescue；
  不复制 live 环境的 kernelctl 状态到目标，不在离线安装阶段误接管 live 内核。
- 四组组件 VM 都须在拔除安装介质后刷新生产 feed 并完成用户态升级，检查未选
  组件没有被意外装回；再覆盖下一版内核的安装、重启确认和回退。
- 另测现有完整系统升级到拆分后的共享包，检查功能与配置保留。安装完成时的
  空间余量还须考虑后续升级缓存、事务日志和并行内核，不能用 1 GiB 预留代替
  实际升级容量验收。kernelctl 回退不等于用户态或组件状态的整体回退。

## 5. 2026-11-16 审查发现及已修复项

下表保留初次审查发现。独立修复已并入安装器 `1-r4`，实际改动和测试范围见
[实施进度与验证记录](installer-components-implementation-validation.md#2026-11-16)。

| 发现 | 证据或触发方式 | 建议 |
| --- | --- | --- |
| 错误跳转到不相关页面 | 无写盘 mock 探针复现 `ports -> lan -> ports`：LAN 数字解析错误被主循环统一退一步；最终校验失败也退到账户页 | 在对应页校验并留在原页；最终校验定位到实际出错设置 |
| 返回会丢掉选择 | `firewall()` 每次固定使用 NAT ON、full-cone OFF、forward ON；网口和 WAN 页面也未完整恢复已填状态 | 以当前答案作为默认值，保留有效输入，避免反复填写密码和参数 |
| 静态 WAN 校验不足 | 调用真实 `validate_answers()`：WAN `192.168.1.2/24` 与 LAN `192.168.1.1/24` 重叠仍通过；WAN `10.0.2.0/24` 为网络地址也通过 | 补静态 WAN 主机地址和 LAN/WAN 网段重叠检查；在 WAN 页提示，不扩展为复杂联网检测 |
| 清理异常可能盖掉原始错误 | `apply.install()` 的 `finally` 收集卸载失败后直接抛新异常 | 保留原始失败阶段与错误，清理失败追加记录；使用现有日志即可 |
| 擦盘确认缺少磁盘身份信息 | 选盘页显示型号和容量，最终摘要主要显示设备路径及分区 | 最终确认补型号、容量和可获得的序列号；保留默认否确认 |
| 完成提示仍只提 USB | 完成消息要求移除 USB，实际已支持光盘 | 统一为移除安装介质，可顺手显示已配置的 LAN 管理地址 |

前两条交互问题和静态 WAN 输入的接受行为已通过无写盘探针核对；清理异常、
磁盘摘要和文案是源码审查发现，未做对应 VM 故障注入或页面截图验收。

## 6. 组件安装验收

未来实施时需要：

- 宿主测试覆盖空选、全选、依赖错误、未知组件、返回保留状态、缺包、坏签名、
  版本不一致和空间不足；确认预检失败没有执行擦盘。
- 检查基础 squashfs 和目标 APK 清单，验证未选组件真正不存在，公共依赖正常。
- 可丢弃 VM 验证四组。每组拔除安装介质后确认 systemd 为 PID 1、overlay 可写、
  procd API 可用，并检查 LAN、DHCP、LuCI、SSH 和第 4 节的滚动升级。

  | 组合 | 额外检查 |
  | --- | --- |
  | 仅基础系统 | 检查保留的路由与运维包。覆盖 DHCP/PPPoE、LAN DNS/NAT、原生 failsafe 控制台及恢复后的正常启动。 |
  | GNOME 无音频 | 同时取消 RDP 和 Flatpak，关闭桌面自启。确认首次启动创建普通用户且桌面未自启。手动启动桌面后检查 GNOME 会话、门户文件选择、录屏或屏幕共享。核对包清单。 |
  | 完整桌面 | 按默认全选安装，检查桌面自启、Audio、IME、RDP、Sunshine、Flatpak 门户、AppImage、virt-manager 和容器基本功能。 |
  | 无桌面的虚拟化及容器 | 验证 libvirt/QEMU、CLI 和 rootless Podman 基本功能，确认没有 GNOME 或 virt-manager。 |

- 在上述用例中分配 BIOS/UEFI、USB/光盘覆盖，复跑 ext4/btrfs/xfs 相关回归，
  检查正常 combined 镜像构建行为和干净镜像边界。复用现有安装器 VM 和纯路由
  网络测试的检查项，为组件 ISO 记录实际使用的 SHA-256 和测试结果。
- 更新指南、验证记录和改动包 release。新功能须有对应运行验证；发布、
  安装到物理设备和用户客户端验收分别记录，不能混称已经完成。

2026-11-16 初次审查运行了现有测试：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/tests/test-openwrt-installer.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/tests/test-installer-optical.py
```

共 11 项，9 项通过、2 项跳过：第一组缺少宿主 UCI，第二组未提供准备好的
目标 root/config，未执行完整冻结工具验证。`test_uci_matrix` 中依赖实际 UCI 的
分支在工具缺失时也未执行，不能将该组结果表述为完整 UCI 运行矩阵通过。
`git diff --check` 在调查时通过。

这些测试覆盖当时的普通安装器。后续的 `1-r4` 构建、systemd-only ISO VM
和应用解耦记录见 [验证进度](installer-components-implementation-validation.md)。
组件 ISO 的安装、启动和滚动升级结果仍待验证。

未来开始时先重新确认需求是否仍相同，核对基础包归属、依赖拆分和离线脚本行为，
再进入实现。不得因本文存在而自动开始构建、发布或部署。
