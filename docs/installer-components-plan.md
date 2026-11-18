# 安装器可选组件：远期计划与源码调查

状态：**远期计划，尚未实现，未安排执行时间。**

记录日期：2026-11-16。本文保存本轮讨论确认的方向和源码调查结果，供以后
实施时接续工作；不是现有安装器的使用说明，也不是新的验证通过记录。
实际行为参见 [安装器指南](installer-iso.md)，历史运行证据参见
[验证记录](installer-iso-validation.md)。未来实施前需重新检查源码、包依赖、
构建配置和产物，不能把这里的日期快照当作届时的现状。

## 1. 已与用户确认的目标

用户希望系统功能可以在安装时选择，并强调不要过度设计。讨论已确认：

- **真正选择安装组件**：未选功能的软件不安装，不只是保留完整镜像后关闭服务。
- 首版覆盖常用桌面组件，并加入虚拟化和容器。
- 安装后先继续使用 APK 管理，不新增统一组件管理菜单或 LuCI 页面。
- 基础系统保留现有路由与运维功能，包括代理、文件共享、监控等既有范围，
  不趁此改成只有基础联网功能的精简发行版。
- 功能选择页默认全部勾选，用户取消不需要的组件。

实现方案沿用现有 GNOME，不新增其他 DE。保持 BIOS/UEFI、USB/光盘、整盘 GPT、
ext4/btrfs/xfs overlay 和后续 kernelctl/APK 升级方式。正常 combined 镜像继续
沿用自己的构建路径和本地 overlay，不随安装器的组件化一起改变。

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
   顶层包、组件依赖和默认选择。逐项归组现有桌面应用、虚拟化/容器的 LuCI 应用
   与翻译包，避免组件取消后又通过其他顶层包被带回。
2. 从同次构建的 APK，在独立目录组装基础 rootfs，不再把完整桌面 rootfs 作为
   安装器 squashfs。沿用共享的 live squashfs/基础安装载荷思路；其中须保留
   安装器运行、分区、文件系统格式化和离线安装必需的工具。
3. ISO 携带基础 squashfs、组件目录和签名离线 APK 仓库。APK 负责依赖闭包，
   不自行编写包求解器，不维护多套完整桌面 squashfs 组合。
4. 只使用同次构建、版本和 ABI 一致的内核、基础系统、索引和软件包；携带公钥，
   不携带私钥。基础系统、仓库和清单的身份要能在预检时核对。
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
- 基础 squashfs 写入并验证后，在挂载的目标 overlay 中安装所选 APK。
  安装脚本、用户组、alternatives 和启动链接按离线安装语义处理；不得意外
  启动 live 系统中的服务。全部步骤成功后才显示安装完成。
- 首次启动完成所需账户、桌面及音频初始化；将桌面初始化与是否自启分开，
  使自启关闭时也能保留正确的组件配置。失败保留请求和日志，支持现有重试机制。

这不是对旧 ISO 格式兼容性的承诺。实施时需给新载荷明确的格式标识，遇到
不支持的载荷应在擦盘前报错；保留已有 ISO，不原地改写已验证产物。

### 需要拆开的现有依赖

- `openwrt-desktop` 目前强制依赖 `gnome-remote-desktop`。RDP 独立可选前，
  必须移除这条强制安装关系，并保证缺少 RDP 时桌面会话正常。
- `xdg-desktop-portal` 目前强制依赖 `flatpak`、`bubblewrap`，并启用了
  `flatpak-interfaces`。GNOME 门户会间接带回 Flatpak；需区分通用门户能力
  与 Flatpak 专属集成，不能只在界面增加复选框。
- GNOME Shell 直接依赖 `pipewire`、`libpulse`；Mutter、门户及 RDP 还依赖
  `libpipewire`。不应把取消 Audio 实现为删除或全局屏蔽 PipeWire。
- `sunshine` 依赖 `openwrt-desktop-audio`；后者依赖 `openwrt-desktop`。
  当前 Audio/IME/Flatpak/AppImage 集成均围绕桌面设计。
- `virt-manager` 依赖 `openwrt-desktop` 和 `libvirt-daemon`。无桌面虚拟化组合
  应选择 libvirt/QEMU、virsh、virt-install 等后端，不默认安装 virt-manager。
- `openwrt-podman-rootless` 没有桌面依赖，可用于无桌面组合；用户登记仍是
  显式操作，不因安装包而自动为普通用户授予额外权限。

这些是 2026-11-16 的源码调查结果，不是拆包后已通过的运行验证。

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
- RDP 依赖拆分必须检查旧 world 的升级求解结果，保留已有包、凭据、用户服务
  与配置；portal 拆分必须保留已安装 Flatpak 的接口能力，不能全局关闭接口来
  实现可选组件。共享包变化同样影响普通 combined 镜像和现有设备。
- 保留内核首次接管、版本化内核并行安装、启动计数、确认、回退与 rescue；
  不复制 live 环境的 kernelctl 状态到目标，不在离线安装阶段误接管 live 内核。
- 四组组件 VM 都须在拔除安装介质后刷新生产 feed 并完成用户态升级，检查未选
  组件没有被意外装回；再覆盖下一版内核的安装、重启确认和回退。
- 另测现有完整系统升级到拆分后的共享包，检查功能与配置保留。安装完成时的
  空间余量还须考虑后续升级缓存、事务日志和并行内核，不能用 1 GiB 预留代替
  实际升级容量验收。kernelctl 回退不等于用户态或组件状态的整体回退。

## 5. 同轮审查发现的独立小改进

这些可以在组件化之前独立修复，不应成为必须一起实施的大改造。

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

## 6. 计划验收与本次证据边界

未来实施时需要：

- 宿主测试覆盖空选、全选、依赖错误、未知组件、返回保留状态、缺包、坏签名、
  版本不一致和空间不足；确认预检失败没有执行擦盘。
- 检查基础 squashfs 和目标 APK 清单，验证未选组件真正不存在，公共依赖正常。
- 可丢弃 VM 验证四组：仅基础系统、GNOME 无音频、完整桌面、无桌面的虚拟化＋容器。
  拔除安装介质后启动，检查 LAN、DHCP、LuCI、SSH，再按组合检查桌面、音频、
  虚拟机和容器基本功能。无音频桌面仍需检查录屏/屏幕共享所需的公共路径。
- 在上述用例中分配 BIOS/UEFI、USB/光盘覆盖，复跑 ext4/btrfs/xfs 相关回归，
  检查正常 combined 镜像构建行为和干净镜像边界。
- 更新指南、验证记录和改动包 release。新功能须有对应运行验证；发布、
  安装到物理设备和用户客户端验收分别记录，不能混称已经完成。

本轮调查运行了现有测试：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/tests/test-openwrt-installer.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/tests/test-installer-optical.py
```

共 11 项，9 项通过、2 项跳过：第一组缺少宿主 UCI，第二组未提供准备好的
目标 root/config，未执行完整冻结工具验证。`test_uci_matrix` 中依赖实际 UCI 的
分支在工具缺失时也未执行，不能将该组结果表述为完整 UCI 运行矩阵通过。
`git diff --check` 在调查时通过。

这些测试针对**现有安装器**，不证明本文的组件化方案可用。本次没有修改功能代码、
构建新软件包/ISO、运行 VM、联系路由器、发布 feed、部署或重启系统。

未来开始时先重新确认需求是否仍相同，核对基础包归属、依赖拆分和离线脚本行为，
再进入实现。不得因本文存在而自动开始构建、发布或部署。
