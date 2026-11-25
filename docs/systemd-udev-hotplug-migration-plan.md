# x86/64 的 udev 接管与 OpenWrt hotplug 兼容层实施交接

**交接日期：2026-11-25。状态：四个实施批次及上游合并审查工具已完成实现，主机单测（142/142）、候选 APK 构建与第 5 节全部隔离 KVM VM 验收（核心 7 阶段 + Suite A 扩展设备/故障/TPM2 + Suite B 纯路由 3-VM PPPoE/failsafe + Suite C GNOME 51/Plasma 6.8.3/音频/FreeRDP 3/Sunshine）已全部通过（见[迁移验证记录](systemd-udev-hotplug-migration-validation.md)）；LAN feed 发布与物理路由器实机安装/重启仍待单独授权执行。** 本文供接手实现、评审与验收的工程师或 agent 使用。现行架构和历史验证分别见[设备管理边界](systemd-udev-boundary.md)和[既有验证记录](systemd-udev-boundary-validation.md)。历史记录中的 VM、路由器结果仅适用于当时的版本。

## 1. 接手时先确认的决定

目标是让正常启动后的硬件事件由 udev 识别，设备权限和链接由明确的规则设置，本项目的设备策略由所属功能包执行。**同一项状态只允许一个写入者。** 保留 OpenWrt 提供给上游包、第三方包和用户的 hotplug 接口。按设备状态和策略的归属验收；脚本个数和事件速率不能代替竞态验证。

| 已与用户确认 | 实施含义 |
| --- | --- |
| 迁移设备规则和本地策略 | 包含 render、KVM、virtio 链接，以及 DRM 触发的桌面启动、音频 ACL、Sunshine 虚拟输入授权。 |
| 为兼容桥增加断线缓冲 | 进入桥接的设备事件先进入本次启动的有界队列。procd/ubusd 短暂停止期间仍可接纳，恢复后补发尚未开始的记录。 |
| 执行中崩溃的记录隔离并报告 | 首次对外通知或执行脚本后就可能产生副作用。仓库可以控制自己的处理器，无法推断任意第三方脚本是否已完成挂载或重启。执行结果不明时交给操作员明确处置。 |

实施范围是 `CONFIG_OPENWRT_SYSTEMD` 下 x86/64 的正常系统，覆盖桌面及纯路由配置。devtmpfs 创建基础节点；udev 管权限、链接、属性和 seat。网络命名、地址、路由、PPPoE、防火墙和 Wi-Fi 重试归 netifd 及现有 OpenWrt 处理器；根和 overlay、UCI 挂载及热插拔盘归 fstools/blockd；LED 配置保留原入口。preinit/failsafe、无 `DEVPATH` 的合成按键、驱动加载继续各走现有路径。非 systemd 目标保留上游规则。纯路由镜像只需通用规则和兼容桥，所有桌面策略随各自的包安装。

## 2. 已查明的实现和基线

### 可复现的起点

| 仓库 | 本地提交 | 本地记录的上游基线 |
| --- | --- | --- |
| 主树 `main` | `8f87d6af5af9` | `origin/main` 的 `ce51f2ff0f34` |
| `feeds/packages` 的 `master` | `c983b8adf7bf` | `origin/master` 的 `ea11c8e94b57` |

当时的配方固定 procd `fb611687`、netifd `a1e39a45`、fstools `5e371ecf`。接手时从各自 Git 历史和配方重新取得版本。主树和 feed 是独立仓库。在上述主树基线上，对比 `origin/main` 后，`/sbin/hotplug-call` 的源码、`hotplug.json` 和 `hotplug-preinit.json` 三个文件内容一致。与设备分发有关的分支差异主要在 native 专用 JSON、udev 规则和 procd quilt 补丁。[procd 配方](../package/system/procd/Makefile) · [netifd 配方](../package/network/config/netifd/Makefile) · [fstools 配方](../package/system/fstools/Makefile)

可在仓库根执行以下只读基线检查。组装目录反映最近一次构建；切换 checkout 或 profile 后应以该次 APK 与镜像重新核实。

```sh
git log -1 --oneline HEAD
git log -1 --oneline origin/main
git -C feeds/packages log -1 --oneline HEAD
git -C feeds/packages log -1 --oneline origin/master
git diff origin/main HEAD -- package/base-files/files/sbin/hotplug-call \
  package/system/procd/files/hotplug.json package/system/procd/files/hotplug-preinit.json
rootfs=build_dir/target-x86_64_glibc/root-x86-systemd
find "$rootfs/etc/hotplug.d" -mindepth 1 -maxdepth 2 -print | sort
rg -n 'virtio-ports|KERNEL=="renderD\*"|KERNEL=="kvm"' \
  "$rootfs/usr/lib/udev/rules.d/50-udev-default.rules"
python3 scripts/tests/test-procd-units.py
python3 scripts/tests/test-systemd-udev-boundary.py
```

本次交接复跑后两项，分别为 **9/9 和 3/3**。当前桌面组装树在 `/etc/hotplug.d` 有 **14 个目录、23 个脚本**。分布为 `iface 9`、`block 2`、`drm 2`、`ieee80211 2`、`ntp 2`，以及 `acme/leds/misc/net/sound/virtio-ports` 各 1 个；`dhcp/neigh/tftp` 为空目录。9 个 iface 脚本涉及 netstate、SQM、TEQL、firewall、nlbwmon、miniupnpd、Samba、wsdd2、Passwall。仅 iface、NTP 和 ACME 已占 12 个。**空目录也有意义**，procd 依据目录注册 ubus 对象，dnsmasq 可向当前没有脚本的对象投递。

### 三条入口，分别保留其调用契约

| 入口 | 当前路径与行为 | 接手者尤其要保留的语义 |
| --- | --- | --- |
| 内核设备事件 | udev 加工 → `90-openwrt-hotplug.rules` → `openwrt-udev-forward` → `procd.udev event` → `hotplug_inject()` → ubus 通知、native JSON 和脚本队列 | 按目录动态匹配，另有固件与 USB 串口特例。注入端把 `DEVNAME=/dev/…` 还原为内核风格的相对名称。units 模式忽略普通 raw 事件，直接保留无 `DEVPATH` 的合成按键。 |
| 程序直接调用 shell | netifd 的 `interface-event.c:run_cmd()` 运行 `hotplug-call iface`，传 `ACTION/INTERFACE/DEVICE/IFUPDATE_*`；blockd 也会直接调用 `hotplug-call mount` | `hotplug-call` 设置 `HOTPLUG_TYPE`、从 `DEVPATH` 得到 `DEVICENAME`，在子 shell 中按文件名顺序 source 各脚本。PPPoE 重拨或路由更新可以发生在同一块持续在线的网卡上。 |
| 程序直接调用 ubus | ntpd 调 `hotplug.ntp call`；dnsmasq 把 DHCP、邻居及 TFTP 事件投到对应 `hotplug.<type> call` | `hotplug-dispatch.c` 的此方法接受字符串数组 `env`，异步逐个执行脚本。设备桥的 `procd.udev event` 接受键值表 `env`。按各自原有的环境及同步语义测试，也要保留 `hotplug.<type>` 订阅通知。 |

普通硬件事件匹配的是目录是否存在；原脚本不要求可执行位，管理员还可以动态安装脚本。native JSON 为固件依次排 `hotplug-call` 和 `load-firmware`，对匹配的 `usb-serial` 节点映射到 `tty`。同名目录里的自有脚本被迁走后，后装的第三方处理器仍要收到事件。[转发规则](../package/system/procd/files/90-openwrt-hotplug.rules) · [native JSON](../package/system/procd/files/hotplug-systemd.json) · [shell 入口](../package/base-files/files/sbin/hotplug-call) · [NTP 入口](../package/utils/busybox/files/ntpd-hotplug)

在 [130-systemd-transient-units.patch](../package/system/procd/patches/130-systemd-transient-units.patch) 中，可按符号定位 `udev-forward.c`、`udev_event()`、`hotplug_inject()`、`procd_systemd_ubus_ready()` 和 `udev_coldplug()`。完整上下文见本次构建展开的 `build_dir/target-x86_64_glibc/procd-default/procd-*/`，改动应落在配方和 quilt 补丁。当前 forwarder 找不到 ubus/端点时返回 0，调用超时为 5 秒，失败可记日志后返回 0。接收端在注入后即可返回成功；真正执行要经过 `plug/hotplug.c` 的 `queue_add()/queue_next()/queue_proc_cb()`。**ubus 成功、进程退出、第三方副作用成功是三个不同的观测点。**

启动时 procd 待 ubus 对象就绪后，每次启动请求一次全设备 `add` 回放。`/run/procd-udev-coldplug` 也会在 45 秒兜底时创建，仅代表可以继续启动。`udevadm settle` 等到 udev 处理结束，下游脚本仍可在跑。桌面另有定向回放、GPU 驱动探测及有界 TPM 等待；`systemd-udev-trigger.service` 随包安装，当前默认没有启用它，单写 `After=` 不会拉起它。不得以额外全量回放、全局 settle 或加长超时代替顺序修复。[procd unit](../package/system/systemd-openwrt/files/openwrt-procd.service) · [桌面定向回放](../package/custom/openwrt-desktop/files/openwrt-desktop-coldplug.service) · [GPU/TPM 探测](../package/custom/openwrt-desktop/files/desktop-gpu-coldplug)

## 3. 按批次实施

### 第 1 批 · 建立竞态基线

1. 对桌面、纯路由两种 profile 分别记录实际 APK、最终 rootfs、挂载的管理员覆盖、启用的 unit、规则排序和冷启动时序。清点每个受管对象的全部写入点，包括热插拔、init、setup、LuCI 后端、APK 安装钩子。使用隔离构建环境保留工作树现有 `.config`。
2. 在隔离 VM 采集 boot ID、单调时间、`SEQNUM/ACTION/DEVPATH`、udev 完成、脚本进入/退出和最终节点状态。分别标记真实事件、procd 启动回放和桌面定向回放；不要用设备名与动作合并不同事件。
3. 用对照镜像复现 render 的两次赋权、libvirt 启动再次改权限、virtio 同路径链接的重复创建，以及手动停止与 DRM `change` 的交错。后者从代码上可见检查与启动分离，是否复现及具体时序应如实记录。把基线、候选结果及失败样例写入新的迁移验证记录，与历史验证分开。

### 第 2 批 · 消除权限和符号链接的重复写入

| 对象和证据 | 实施动作 | 核对点 |
| --- | --- | --- |
| DRM render。最终 `50-udev-default.rules` 给 `renderD*` 设 `render:0666`。随后 `drm/zz-libvirt-render` 改为 `root:render 0660`，libvirt prepare 启动时又扫一遍 | 由 **libvirt-daemon** 随包安装 udev 规则。移除本包 hotplug 赋权、prepare 的节点扫描；保留 prepare 的目录、密钥等无关职责 | udev 完成时即有目标权限。检查实际 ACL、qemu 用户及获准桌面用户的设备访问。未装 daemon 的镜像保留发行版默认。 |
| KVM。默认规则含 `GROUP="kvm", MODE="0666", OPTIONS+="static_node=kvm"`，同一 prepare 会改为 `root:kvm 0660` | 在同一功能包提供规则，同时覆盖静态节点和模块后加载，去除 prepare 的节点改写 | 冷启动、热加载、服务重启后分别检查 mode、组和实际打开结果。确保普通未授权用户与授权组结果符合策略，其他设备如 `vhost-vsock` 仍按自身规则处理。 |
| virtio。udev 已有 `SYMLINK+="virtio-ports/$attr{name}"`；packages feed 中 `virtio-console-helper` 的 `00-virtio-ports` 再手工 `ln -s` | native 构建只省去这一脚本，保留包名、依赖、兼容目录、非 systemd 分支。单独安装的 `qemu-ga` 仍用自己的 `10-qemu-ga` 响应事件 | 热拔后链接消失，同名端口插回后指向新节点；装有 qemu-ga 的客体实际响应 guest-agent 请求。 |

关键入口为 [libvirt 打包](../package/custom/libvirt/Makefile)、[render hook](../package/custom/libvirt/files/libvirt-render.hotplug)、[libvirt prepare](../package/custom/libvirt/files/libvirt-openwrt-prepare)、工作区独立 feed 的 `feeds/packages/utils/qemu/Makefile` 下两个子包。现有 [procd 单测](../scripts/tests/test-procd-units.py) 专门约束通用 hardware-support 包不能全局收紧 KVM/render；把测试扩展到“装 daemon”和“未装 daemon”两种组合。已有节点随包升级时只重载规则和定向处理涉及的节点。核对 APK 对旧文件和管理员改过的 hook 的实际处理；有本地冲突须提示并保留内容。

### 第 3 批 · 迁移桌面、音频、Sunshine 的本地设备响应

每个功能包各有一个 root 私有的 `/run` 变化标记及配对的 systemd `.path`/oneshot。udev worker 做短时原子标记后退出。worker 服务先取走此次标记，再读取当前设备和配置；运行中新来的标记会在退出后触发下一轮。这样一批声卡节点的出现可合并处理，持续在线设备的 `change` 也能触发。失败记录原因并有界退避，避免一直满足的 path 条件导致忙循环或触发启动限流。考虑已存在标记时才启用 watcher 的情况。长任务留给服务。`SYSTEMD_WANTS` 的设备首次可用语义不足以覆盖每次变化。[udev 手册](https://www.freedesktop.org/software/systemd/man/latest/udev.html) · [device 激活语义](https://www.freedesktop.org/software/systemd/man/latest/systemd.device.html) · [path 重新检查及限流](https://www.freedesktop.org/software/systemd/man/latest/systemd.path.html)

| 功能 | 源码入口及已有行为 | 实施与竞态约束 |
| --- | --- | --- |
| DRM 和桌面 | [desktop.hotplug](../package/custom/openwrt-desktop/files/desktop.hotplug) 在外层检查手动停止标记后调用 start；[desktop.init](../package/custom/openwrt-desktop/files/desktop.init) 在成功启动后清标记、在 stop 时写标记；[desktop-ctl](../package/custom/openwrt-desktop/files/desktop-ctl) 另有切换/管理入口 | 自动启动、手动启动/停止、切换复用现有桌面操作锁，在锁内重查配置、标记及当前会话。自动请求无权清标记，显式启动可恢复。避免跨相互等待的 unit 持锁。活动 GNOME/Plasma 会话处理自身显示器变化。 |
| 音频 ACL | [权限助手](../package/custom/openwrt-desktop-audio/files/desktop-audio-permissions)、`desktop-audio-permissions.init`、[setup](../package/custom/openwrt-desktop-audio/files/desktop-audio-setup) 和 `sound/95-desktop-audio` 都涉及同一权限状态。ALSA 基础组已有 [udev 规则](../package/system/hardware-support/files/udev/60-openwrt-audio.rules) | udev 设基础属组和 mode；功能服务只收敛受管用户 ACL。所有调用复用同一实现和锁，在锁内读最新用户，清旧 UID，原子更新运行态 UID 文件。设备在枚举中拔出时继续处理其余节点。显式 setup 保留同步反馈。 |
| Sunshine | [权限助手](../package/custom/sunshine/files/sunshine-permissions) 同时碰 `/dev/uinput` ACL、程序执行 ACL 和 KMS capability。入口包括 misc 热插拔、[setup](../package/custom/sunshine/files/sunshine-setup)、init、[APK 钩子](../package/custom/sunshine/Makefile) 及 desktop-ctl 修改 capture 的路径 | 设备事件只按有效注册和当前用户设置 uinput ACL，切用户或撤权清理旧授权。程序属组、执行 ACL、KMS capability 由安装、显式授权和 capture 模式切换共用的逻辑负责。确认 portal 插拔不会获得 KMS capability，保留已有注册检查与同步错误反馈。 |

保留显式 `hotplug-call` 和 `hotplug.<type>.call` 的可观察行为。需要时在原编号位置留薄适配，调用同一份策略。udev 已提交的事件带内部来源标识，适配层避免重复提交。如果后续脚本依赖前一编号的完成结果，在兼容执行端等待对应任务。先检查依赖链，避免桌面冷启动反过来等待自己。用真实设备路径和两个直接入口分别验证。桌面串行化从 [rc.common](../package/base-files/files/etc/rc.common) 和 [procd_lock](../package/system/procd/files/procd.sh) 的现有加锁点入手，明确子进程继承锁的范围，避免由已持锁的入口再次调用需要同一把锁的 init 脚本。

### 第 4 批 · 有界缓冲和故障恢复

沿用目录筛选和 procd 的 JSON/脚本执行器。在 native 模式增加本地入队和 procd 消费模块，集中在独立 quilt 补丁；无需新常驻守护进程。**同一事件只走一个生产路径**，在线和断线都先写 root 私有的 `/run/openwrt-hotplug/`。保持 `procd.udev event` 的旧方法和参数可用，以支持混合版本。

| 状态或边界 | 实现和验收约定 |
| --- | --- |
| 接纳 | 保存有界、结构化的事件环境快照，原子提交完整记录。对真实内核事件以 boot ID 与 `SEQNUM` 识别同一次投递。不同序号的合法回放分别处理；直接软件调用保留原语义。并发写入时以成功接纳顺序排序，同设备的 add/change/remove 保留边沿，不能因当前在线跳过较早积压。 |
| 等待 | procd 在 ubus 对象就绪后先挂监听再扫描存量，重连亦如此。记录留在跨 procd/ubusd 重启的目录中。挂起期间无需 udev 等待总线。覆盖“已写入，进程尚未收到唤醒”和“扫描时又有新事件”两个窗口。 |
| 开始与结束 | 单次只向兼容执行器提交一条受缓冲记录。在第一次可能产生副作用的 ubus 通知或脚本之前原子标为执行中；本事件的 JSON 动作、脚本子进程走到完成边界才退休。处理 fork/入内存队列失败、退出异常和无匹配命令。现有 shell 对每个脚本的退出值可见性有限，完成计数只表示可观测的执行边界。 |
| 执行中崩溃 | 将此条转入隔离区并记录最后阶段。暂缓同一设备依赖其结果的后续事务，其他设备可继续。提供只读状态查询及由操作员显式执行的处置入口。故障注入需证明外部副作用不会因恢复而再次自动触发。 |
| 旧设备与时效 | 积压恢复时核对原设备实例，例如可用的块设备 disk sequence，避免对复用了名字的新盘执行旧挂载。已消失设备的 remove 仍应按其原语义处理。对固件检查原请求身份、有效期和 sysfs 实例；过期或无法确认时记录原因，不能向新实例写数据。 |
| 压力与寿命 | 初始上限 2,048 条、8 MiB 编码载荷，先触达者生效。满时保留已接纳项、明确拒绝新项并限频告警。损坏记录和隔离区单独受控，防止撑满 tmpfs。报告积压数、最老年龄、已派发、隔离、过期、溢出数；日志只记录诊断所需字段。缓冲仅跨服务中断，重启后依既有 coldplug 重建设备状态。 |

## 4. 上游合并、升级与回退

1. **每次合并查行为差异。** 实现一个只读审查工具，输入主树和各 feed 合并前后的真实提交。列出增删改的 stock/preinit JSON、向 `hotplug.json.d` 安装片段的配方、硬件支持包、hotplug 脚本安装路径、procd 固定版本、systemd 默认及本地筛选规则。可检测的新增第三方脚本走兼容冒烟；每项 JSON 行为记录“已有 udev 等价物”“兼容层执行”或“本目标不适用”及理由。未分类项阻止候选通过验收。不要依靠文件名或 Git 是否冲突判断等价。
2. **警惕安静的行为分叉。** stock `hotplug.json` 会 include `/etc/hotplug.json.d/*.json`，native `hotplug-systemd.json` 并不执行这些片段。当前 rootfs 里有 audio、video、accel、input、KVM 等 JSON；硬件支持包按项目需要另装 udev 规则。上游提交 `e06e3a621b` 把 ALSA 权限拆到 audio-support 就是可复现样例。合并后应比较最终成员组、权限和辅助程序，而非简单复制 JSON 或整套 systemd 规则。现有网络 `RUN+=systemd-sysctl`、自动模块加载和挂载策略均有明确归属。[hardware-support 配方](../package/system/hardware-support/Makefile) · [本地筛选的 99-systemd.rules](../package/system/systemd/files/99-systemd.rules)
3. **限制补丁面。** 保持 `/sbin/hotplug-call`、目录约定、两类 ubus 方法及其通知语义。procd 升版时在新固定源码上应用 quilt 并实际编译；systemd 升版时检查新默认规则、数值顺序和最终包内容。主树与 packages feed 分开提交，feed 补丁镜像、基线按仓库惯例更新。检查变更 APK 的有效 release 和不可变身份。[本地构建约定](local-build.md) · [APK 重建约定](apk-rebuild-release.md)
4. **分两步切换协议。** 先交付能接受旧 ubus 注入并消费新队列的接收端，再切换生产端。新镜像在启动后首轮正常 udev 分发前确定模式。在线升级应以正在运行的接收端能力为依据，安装了新二进制并不说明旧进程已具备能力。本次启动一旦选择队列，后续断线保持入队。回退前排空或显式处置待办与隔离记录。验证新旧进程与包交错运行、规则重载、管理员改过的旧 hook，以及安装/卸载功能包后既有节点的最终权限。

## 5. 验收矩阵

以下均为**候选实现的待办项**。将来按源码、包/镜像、VM、真机及真实客户端分别记录结果、版本和证据路径。已复跑的两项基线测试在第 2 节。

| 层次 | 必测场景及通过条件 |
| --- | --- |
| 源码、包、镜像 | 复用现有 procd 和 udev 边界测试，并覆盖桌面 coldplug、音频、Sunshine。加入并发入队、队列状态转换、溢出、watch/scan 交错和手动停止测试。检查桌面、纯路由最终 rootfs 和实际 APK 的规则、链接、依赖和包归属。非 systemd 构建保留 stock JSON、QEMU helper 及 preinit 路径。 |
| 权限及端口 | 隔离 VM 至少 3 次冷启动、20 轮备用设备移除与重建。对 render/KVM 检查 mode、ACL、授权和无授权用户的真实打开结果，记录 udev 完成及 libvirt 启动后的状态。测试有/无 libvirt-daemon、运行中安装与升级。virtio 同名端口重建后链接正确，QEMU guest agent 实际通信成功。 |
| 桌面策略 | 手动停止与 DRM 事件并发，已停止的会话不会复活；显式启动成功，运行中的会话不重复启动。音频用户 A 换 B 同时热插设备后，B 可用且旧受管 ACL 清除。Sunshine 的 portal/KMS、撤权和虚拟输入分别验证。GNOME/Plasma 各完成一次实际登录与输入；有音频/串流的配置用真实客户端验证。 |
| 上游 API 和故障注入 | 临时安装两个有顺序依赖的第三方脚本。分别从真实设备、直接 shell 和 ubus 注入，核对每条入口原有的环境、通知、顺序和调用次数。在 ubus 暂停、procd 尚未开始、外部副作用已写入但未退休三个窗口制造中断。前两类恢复补发，第三类隔离且副作用计数不再增加。另测队列满、隔离设备不阻塞其他设备、同名复用、过期固件、损坏记录和版本混装。 |
| 启动和路由 | 纯路由 VM 加独立客户端，测 DHCP、DNS、NAT、管理登录、PPPoE 断线重拨、防火墙更新及恢复。检查每次正常启动一次全量回放，procd 重启不再全量回放，纯路由不等待桌面策略。备用数据盘走 fstools 的挂载/移除；另启 preinit/failsafe 验证。保留既有设备边界测试对 TPM 和关键设备单元的约束。 |
| 发布与物理验收 | 按仓库流程核验签名 APK、目标机预检与精确升级模拟。物理验证单列，优先用备用设备，分别记录现有桌面、LAN/WAN 和客户端行为。发布、设备安装、服务/桌面重启、物理路由器重启需各自授权。对缺少硬件、未执行的噪声/并发场景写明验证缺口。[发布预检](publication-readiness.md) |

可复用的入口如下，guest 脚本应在隔离客体运行。已有 procd guest 测试会重启 procd 并带动 rc 服务队列，包括 dnsmasq；不要把这个操作当作真机只读检查。

- [procd guest](../scripts/tests/procd-units-guest.sh) 已有运行时新增 `mem/99-unitprobe`、真实触发 `/sys/class/mem/null`、等待结果并验证单次投递的范例。以它扩展第三方脚本和故障探针。
- [纯路由 PPPoE/failsafe VM](../scripts/tests/test-systemd-router-pppoe-vm.py)、[输入热插拔](../scripts/tests/test-input-hotplug.py)、[GPU 探测](../scripts/tests/test-desktop-gpu-coldplug.py) 和 [APK 事务 VM](../scripts/tests/test-apk-transaction-vm.py) 可分别覆盖启动、设备生命周期和滚动切换。
- [桌面会话](../scripts/tests/test-desktop-sessions.py)、[音频](../scripts/tests/test-desktop-audio.py)、[音频 guest](../scripts/tests/desktop-audio-guest.py)、[Sunshine](../scripts/tests/test-sunshine-gnome.py)、[Plasma VM](../scripts/tests/test-kde-plasma-vm.py) 和 [libvirt guest](../scripts/tests/libvirt-guest-smoke.sh) 提供功能入口。读取各脚本参数，分别安排源码、guest 和真实客户端验收。

**接手后的第一项交付**是第 1 批的“对象—写入者—触发顺序”清单及可复现 VM 基线。随后逐批提交、逐批对照。最终应能演示：受管状态只有一个写入者；中断后未开始的已接纳事件可补发，结果不明的副作用不会自动重复；上游新增脚本直接可用；纯路由启动和数据面通过回归。任何一项失败，保留失败样例并在该批修复。
