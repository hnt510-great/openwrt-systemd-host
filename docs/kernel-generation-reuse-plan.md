# 发布系统复用已发布内核：实施计划与交接

**交接日期为 2026-11-23。状态为已完成只读调查和设计，待实施。** 适用目标为本 checkout 的 x86/64、glibc、APK、native systemd。维护者已选择同时解决两个问题：rolling 和 VM 介质默认复用已发布内核，并缩小内核输入指纹。日常入口继续使用 `./scripts/build-and-publish.sh --rolling -j16`。用户态包的构建新鲜度、不可变 APK、当前的并行安装和 kernelctl 回退机制都是验收条件。

**接手后的第一步是复核并保全基线。** 在修改 Make 规则、切换指纹算法、更新 feeds、清理 tmp 或运行任何预留代次的命令之前，完成第 4 节第一步。此时最有价值的证据是旧算法仍能解释当前发布的 85。本文记录观测值和复核方法，实际迁移应从当时有效的签名快照取得文件。

## 1. 84 → 85 事件与证据

维护者报告的顺序为 VM 验证期间执行普通 `make package/install target/install` 生成配套 ISO，随后 rolling 输出 “Recorded generation differs from existing compiled image/config/timestamp; reserving an unused generation.” 并分配 85。源码可确认该消息对应的分支。该分支把多种失败合并成一个布尔值；目前没有保留下来的逐项失败值可证明 84 当时究竟在哪一项失配。

本次对实际发布仓库、本地构建树和旧函数的只读检查如下。Git HEAD 为 `b323dc7677dfef5c77c999665bc8ac2e51ec646e`，这是检查时的 checkout 标识。不能据此反推 84 构建使用的源码提交。

| 观测项 | generation 84 | generation 85 |
| --- | --- | --- |
| 发行 release | `7.3.5-84-openwrt` | `7.3.5-85-openwrt` |
| staged vmlinuz 中嵌入的时间 | `2026-11-22 13:46:22 +0000` | `2026-11-23 10:00:53 +0000` |
| 已发布 vmlinuz SHA-256 | `eb7cf93eb8c10ab851ae41074c90f5afd8dde783695a12c8ae9fbf4bd53cea79` | `2a1ff59d1f2972f51f1c981dc456c83202f694bdc9a94076fb0322229573dd53` |
| 已发布 linux-image APK 整包 SHA-256 | `5807d176879ea740e5abab34edf7e9d02466ba184e48e817c2d7bd218696b8d2` | `ae59c53789bd57ac5d5e6bb7e8d816c00a82ff2f78f4f447f1657ff41dce22e8` |

- 两代 image APK 中的内核 config 哈希均为 `96e08c63228b6226a0e090ed5784de57a9afcc3726595bd6adbfcfc519f2e5ff`，System.map 哈希均为 `dfaaaa01c117910e18929026b925266c352d1612090ea02311db628aa12dac14`。按 release 归一化路径后，386 个模块路径完全对应，逐文件哈希相同的数量为零。代次进入 KERNELRELEASE，模块与镜像须按 release 整套使用。这个比较无法证明源码完全相同或两个 release 的模块可以互换。
- `/srv/openwrt-feeds/public/kernel-upgrades` 当时指向 `kernel-snapshots/1795428722524507124`，manifest sequence 为 85，保留 83、84、85。`public/current` 指向 `snapshots/20261123T101121.562906Z`，用户态 ABI 标识为 `7.3.5~5eaacd40bf4a752328abbcfbf2b75c1e-r1`。实施时重新解析两个 alias，不能把本文的快照名写死。
- 工作树 `.config` 的序号为 85，`tmp/.kernel-publication-inputs.json` 的 schema 为 1、phase 为 built。旧算法在现有 `tmp/.packageinfo` 和无额外 Make 参数下实测 `same_inputs=True`、`generation_matches_compiled_image=True`。source 摘要为 `4fe5fab04cbea02ab5dfa06d2b25f38446233cb3cb123c371b6b5b8d14df181f`，tools 摘要为 `6ed9afddb2b046a3c6d7f3f705550b9b15dbdf43872e422df20484cfc705604f`。
- 从 kernel 频道取当前 image、headers、`linux-image-openwrt`、`kernel-dev-headers`、虚拟 `kernel` 共 5 个包。从用户态频道按当前配置选出的 `kmod-*` 找到 275 个 `1000.85.*` 包。共 280 个发布 APK 均用 staging 的 apk 和仓库密钥目录验证通过，整包 SHA-256 均与对应本地输出一致。275 是配置包数量，386 是镜像中的模块文件数量。这次核验覆盖上述集合；没有运行生产升级模拟、VM 或查询实体机的运行内核。
- 客户端观察要按起点解释。已发布的 85 仍可被运行 84 的设备选中。目标是 85 客户端在下一次纯用户态更新后继续运行 85，同时正常收到新用户态包。

## 2. 当前调用链及容易漏掉的消费方

以下文件和函数均指交接时的实现，行号仅供定位。

| 入口 | 当前行为与实施意义 |
| --- | --- |
| [代次决策](../scripts/build-and-publish.py)，`prepare_sequence()`、`generation_matches_compiled_image()` | 从工作配置、tmp 记录和发布 manifest 决定是否复用。若本地没有该代 image APK，后一个函数直接返回 True；有 APK 时检查唯一 compiled release、匹配的 APK 名、x86 boot header 时间后缀，以及 APK 内 vmlinuz/config 与本地文件哈希。它没有直接验证完整已发布代次。失败时从 `max(current, published+1)` 搜索可用号。现有时间校验针对镜像内容，调整 mtime 不能修复它。 |
| [输入指纹](../scripts/kernel-build-inputs.py)，`fingerprint()` | 现状已经计算包请求的内核 Kconfig、已选模块的 provider 和 build-deps，已排除序号本身，并区分 host 诊断摘要与 staged 工具摘要。但目录扫描包含整个 generic、板级目录、toolchain、通用 package Makefile 和迁移表；纯 ISO 配方与非活动系列补丁也会计入。 |
| [Make 的内核时间](../include/kernel.mk)、[编译与安装](../include/kernel-build.mk) | 普通 make 可由 SOURCE_DATE_EPOCH 经 Perl gmtime 生成时间字符串。wrapper 从本代记录传入 KBUILD_BUILD_TIMESTAMP。target/install 依赖 .image，其规则含 FORCE 并调用 Kernel/CompileImage；制作介质可能再次进入内核目标。仅修 Python 分配逻辑会遗漏这个入口。 |
| [包级 staging](../include/package-pack.mk)、[内核文件归集](../scripts/kernel-package.py)、[bundle](../scripts/kernel-bundle.py) | pack hook 将内核、模块和头文件归集到 kernel-bundle/<release>。bundle 汇总已选模块后签包，同名 APK 已存在且整包字节不同会拒绝覆盖。普通 make 可能先改变编译目录，也可能在 bundle 校验处停止。遇到问题要区分编译镜像、staging、bin 中的 APK 和已发布 APK。 |
| [rolling](../Makefile)、[package/merge](../package/Makefile)、`project()` | rolling 运行 package/compile 和 package/kernel-bundle。package/merge 也先执行 kernel-bundle。project 从本地 compiled release、kernel.version 和 bin 构造两套发布输入，验证已选 kmod 版本。复用分支必须向这几处提供同一份已验证输入。单独跳过 kernel-bundle 不足以完成复用。 |
| [x86 介质](../target/linux/x86/image/Makefile)、[介质输出](../include/image.mk) | EFI boot 文件复制 KDIR 中的内核；ISO 构建器另收一次 kernel 路径；installer initramfs 读取 LINUX_DIR/.config；离线仓取自合并后的 PACKAGE_DIR_ALL。三个入口可分别取到不同来源。VM_MEDIA_DIR 标记本轮确实生成了介质，仍需从最终介质中核对内容。 |
| [协调发布](../scripts/build-and-publish.py)，`publish_locked()`、`capture_artifacts()` | 已有冻结 bundle 和 expected inventory、复制后再验哈希、两频道预检、回执及 promotion。继续利用这些边界。kernel 频道还携带 grub、apk 等支持包；支持包独立更新可以令频道快照改变而内核代次保持原值。 |

现有临时工作方式：已编好目标包时，`publish-changed-feeds.sh` 可协调发布现有输出；它仍执行投影、完整性校验和升级预检，也不保证绕开脏内核输出。需要同批 VM 介质时已有 `python3 scripts/build-and-publish.py build-only --vm-artifacts <新目录> -j16`。它会进入完整构建和代次决策。`build --rolling --dry-run` 仍会构建并可能预留序号，不能充当只读诊断。

## 3. 决策规则与接口

| 可证明的情况 | 行为 | 下一步可观察结果 |
| --- | --- | --- |
| 有效内核输入和原代凭据一致 | 按签名和 SHA-256 复用已发布的精确字节 | 包图照常编译用户态；旧 vmlinuz、头文件及对应模块进入发布和介质 |
| 本地编译目录、bin 或 tmp 状态缺失或漂移，发布凭据完好且有效输入仍可证明一致 | 从固定快照构造独立 staging | 输出失配项与复用来源；不写回冲突的同名 APK |
| 当前系列版本、补丁、合成内核配置、模块源码或集合、编译参数、交叉编译器等有效输入变化 | 在锁内预留新代，固定其内核时间 | 失败重试沿用相同预留，完成后才允许发布 |
| 通用打包规则、工具或配置包元数据变更，无法静态排除对内核产物的影响 | 默认保守分配新代；可选对轻量 `kmod-*` 包装做同 release/时间戳隔离候选的安装语义比对 | 确认等价时方可复用原签名 APK；若变更触及按代不可变载荷，或 `kmod-*` 版本变化无法在不改动 `1000.<sequence>.*` / `project()` / tracker 契约下安全表达，一律分配新代 |
| 新建空频道或维护者显式提高序号 | 沿用现有首次分配或显式升号语义 | 单调递增，保留旧代和回退能力 |
| 现存发布无法验证、密钥不匹配、比较范围不完整、或快照在使用前被替换 | 报告阻塞项，保持序号和发布指针 | 修复证据或重新读取当前发布后重试 |

新增只读 `./scripts/build-and-publish.sh --explain-kernel`。在任何 prepare-tmpinfo、写 .config、save_state、make 或发布准备之前分流。输出当前/已发布代次、release、基准快照、可比较的输入组、首批具体变化项、判定与理由。缺少新鲜元数据时输出缺失/过期及刷新方式；若启用候选比对且需要隔离构建时报告“待比较”。只读解释不得伪造确定结论。自动化应能区分复用、新代、待比较、证据不足。显式调整内核时间应作为维护者意图单列；普通发行时间变化只影响介质时间。

在 `reuse=True`（复用已发布代次 `N`）的发布路径上，`apk-upgrade-preflight` 增加**同代零内核载荷触碰断言**：当目标路由器（或同代模拟基线）已运行并安装代次 `N` 时，solver 计算出的升级事务不得新增、升级或重装 `linux-image-*`、`linux-headers-*`、`linux-image-openwrt`、`kernel-dev-headers` 及未发生合法版本演进的同代 `kmod-*`。一旦计划触碰上述按代不可变内核包，预检直接阻断发布。

## 4. 实施顺序

### 第一步：用旧实现取证，准备可恢复的迁移样本

记录工作配置、旧状态、source/tools、嵌入时间、目标和公钥指纹，两频道解析后的快照、对应回执和精确 APK 清单。私有测试目录复制用于迁移的 APK、索引、manifest、公开验证材料及哈希；冻结时避免与可变 bin 或将被清理的快照共用可写文件。避免复制签名私钥、个人 overlay 或把生产快照纳入 Git。已有签名产物可用公钥核验。下例只读，使用 checkout 中旧实现，在仓库根目录运行：

```sh
python3 -B - <<'PY'
import importlib.util
import json
from pathlib import Path

tree = Path.cwd()
spec = importlib.util.spec_from_file_location("publication", tree / "scripts/build-and-publish.py")
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)
state = json.loads(publication.state_path(tree).read_text())
current = publication.INPUTS.fingerprint(tree, publication.configuration(tree), ())
print("sequence", state["sequence"], "timestamp", state["timestamp"])
print("inputs_match", publication.INPUTS.same_inputs(state["inputs"], current))
print("image_match", publication.generation_matches_compiled_image(
    tree, state["sequence"], state["timestamp"]))
PY
```

另对 manifest 选出的 APK 执行 `staging_dir/host/bin/apk verify --keys-dir "$PWD" <APK绝对路径>`、`sha256sum` 和 `apk adbdump --format json`。使用绝对 keys-dir；此次复核中相对的点目录在 verify 中失败。对照发布索引、回执与本地副本，核对包名、版本、架构、依赖、整包哈希，记录选中 kmod 的来源仓。若实施时最新代已经前进，以新基线复核，不回退生产别名。仅凭相同 ABI 或发布目录中还有旧包不能认领一个代次。

### 第二步：建立按代的发布记录，并引入只读决策

在发布端保存版本化、可校验的按代记录。最少包含目标、release、ABI、sequence、固定时间、分项输入指纹，以及按仓定位的 APK 身份和整包 SHA-256；绑定发布公钥、已授权快照与回执。原代基础载荷和配置包各自独立更新的版本须可追溯。还要能解析支持包更新后仍然有效的当前视图。复用数据放在快照保留或同等持久存储范围内，tmp 仅作为预留/重试缓存。

在推送指针前准备记录，并校验和预检实际要推送的两套内容；以现有协调发布的提交边界确认记录生效。中断恢复根据实际别名及回执判定，不能只看“记录文件存在”。解释器和执行器共用同一决策函数。构建前固定所读快照身份，在发布锁内再验一次；另一 checkout 抢先推进后，旧候选须重新决策。部署新记录格式时允许读取历史 manifest 和冻结 bundle，只有明确证据链完整的旧代才可导入。不要用新代码在任意当前树上重算出的新指纹追认旧产物。

### 第三步：按 Make 的实际选择收窄输入

由 Make 输出当前 target/subtarget/series 真正用于构建的版本、源码校验值、补丁序列、覆盖目录和 Kconfig 输入，使用现有 [target 解析](../include/target.mk)、[内核构建规则](../include/kernel-build.mk) 和 package-metadata.pl 的结果。含 testing kernel、feed provider、选中外部模块的生成器/头文件、env/kernel-config、目标编译 flags 和 staged 交叉工具链。保存分组及可定位到条目的摘要，避免只能看到总哈希变化。

将可确认的纯介质配方、其他系列补丁和宿主诊断信息排除在分配条件外。优先落地“持久化按代记录 + 按 Make 实际选择收窄指纹 + 从固定快照统一注入”的核心主线：通过精确收窄输入即可消除绝大多数日常误升代。对于极少改动的底层共享打包规则，主线默认采取保守升代（Fail-closed），避免引入高复杂度的全量内核与模块隔离重编比较器。若对轻量包装或 `kmod-*` 元包启用隔离候选比较，不能仅以路径名断言脚本或工具“只影响包装”，比较范围须覆盖文件集合/内容、权限/属主、符号链接目标、APK 的依赖/provides、安装脚本及触发器等安装语义；签名与归档噪声不能成为旧身份下接纳新字节的理由，候选等价时直接选择原件。修改仅影响 `kmod-*` 元包时，须先满足现有 `1000.<sequence>.*` 版本格式、`project()` 与 tracker 依赖契约；无法在不破坏现有按代约束下安全表达独立升级时，仍统一走新代。

### 第四步：接通 rolling、普通 Make、介质与冻结发布

将“本轮新建”或“指定快照复用”的决定传入子 Make 和独立 staging。对复用集合逐包验证并冻结后，替代 package/kernel-bundle、package/merge、project、artifact capture 所依赖的相应输入。为复用项显式记录来源；其他用户态包继续由本轮 Make 提供身份/路径/哈希。保留分配用户态 rebuild release 后重新计算 rolling inventory 的流程。纯用户态单包构建、整图 rolling、world 和 `--vm-artifacts` 都要经过各自正常入口测试。

普通 Make 仅在匹配目标和 release 时使用已记录的 KBUILD_BUILD_TIMESTAMP。只有内核编译使用这个值，介质自身的 SOURCE_DATE_EPOCH 仍可变化。对 package/install 和 target/install 的两次独立调用也要能取得同一记录。EFI 启动分区、ISO 启动内核、initramfs 所用配置、离线 APK 及装入最终 rootfs 的内核/模块均应来自所选的同一代。只在发布末端替换 image APK 会留下旧介质或造成启动内核与 rootfs 不一致。

### 第五步：迁移和交付

先在独立 checkout、隔离发布目录和一次性 VM 中用第一步样本验证旧记录导入。旧证据不足时，用原 release 和时间戳做隔离构建并校验；完整性不能证明时停止导入，列出待查文件。验证迁移、失败恢复和 solver 结果后，补写配套 validation 记录，分开列出源码测试、真实构建、隔离发布预检、VM 与实体机状态。生产发布、安装、重启沿用独立授权边界。

## 5. 测试矩阵与完成条件

| 场景 | 至少需要看到的结果 |
| --- | --- |
| 同代只改用户态 | 新 APK 的版本和摘要出现在本轮 inventory、候选快照及回执。已安装 85 的模拟系统（及同代路由器预检）收到用户态更新，`apk-upgrade-preflight` 强制断言交易中零新增/升级/重装 image、headers、tracker 或未变更的同代 kmod；代次仍为 85，若预检出现任何按代内核载荷变动则直接阻断。 |
| 复现报告中的顺序 | 在隔离样本中先走普通 package/install 和 target/install，并制造本地嵌入时间或 bzImage 漂移，再跑 rolling。记录具体失配项并复用 85。旧 APK 哈希不变。仅触碰文件 mtime 不能替代嵌入时间测试。 |
| 指纹正反例 | 分别改纯 ISO 配方、未启用系列补丁、宿主诊断工具，应保号。分别改活动系列补丁、已选外部模块、用户态引入的有效 Kconfig、KCFLAGS 和目标交叉工具链，应各自分配一次新代。至少一例在 ABI 标识相同时仍正确升代。 |
| 打包规则与支持包 | 核心打包规则变更在未启用候选比对时保守升代；若启用候选比对，等价重打包复用原字节，而依赖、安装脚本或头文件内容变化不能误判等价。仅 grub 等支持包变化可产生新频道快照而保留相同内核。 |
| 缺失和篡改 | 删除隔离 checkout 的 tmp、本地 image 或构造错误 boot header，可信快照齐全时恢复。破坏快照摘要、签名、kmod 完整性或 tracker 依赖时应阻止提升。只读解释前后对比配置、预留、两个别名。 |
| 重试和竞争 | 未发布的新代构建中断后重试沿用同一时间和序号；两个 checkout 共享测试目的地时过时候选不能覆盖较新发布。模拟第一指针更新后失败，复核回执和恢复后的两指针一致。 |
| 介质实物和 VM（一次性交付验收 vs 日常发布） | **本次功能交付验收**（因改动介质内核注入路径）：解出最终 ISO 和 EFI 镜像中的启动内核，逐个比对签名 image 内 vmlinuz 的 SHA-256；核对离线包和 headers（如选择）；启动 ISO 并离线安装，启动安装后的 guest 和配套 EFI 镜像，检查 `uname -r`、模块目录和至少一个实际可加载模块，留存介质、包和 VM 日志摘要。**后续日常 `--rolling` 复用发布**：遵循 [publication-readiness.md](publication-readiness.md) 常规门槛，以介质内 `vmlinuz`/离线 APK 静态哈希核验与协调发布预检为准，不将每次跑 VM 作为日常发布前置条件。 |
| 真正需要内核升级 | 在独立样本中验证 tracker 带入一套新 image/headers/kmods，旧内核仍可作为 kernelctl 回退项。另测已装 84 的模拟客户端，保留其合法升级到已发布 85 的行为。 |

优先扩展 [test-build-and-publish.py](../scripts/tests/test-build-and-publish.py)。尤其注意当前 `test_changed_compiled_image_with_same_inputs_advances_sequence` 等测试编码了旧策略。按“有可信发布记录可恢复”“真实输入变更”“证据不足”拆成不同用例；保留原来关于重复身份、错误 tracker、回滚、失败重试、已发布旧代不可覆盖的断言。补充 [test-kernel-build-inputs.py](../scripts/tests/test-kernel-build-inputs.py) 和 [test-kernel-bundle.py](../scripts/tests/test-kernel-bundle.py)。此后再跑介质和升级链路：

```sh
python3 scripts/tests/test-kernel-build-inputs.py
python3 scripts/tests/test-kernel-bundle.py
python3 scripts/tests/test-build-and-publish.py
python3 scripts/tests/test-kernel-apk-policy.py
python3 scripts/tests/test-installer-components.py
git diff --check
```

VM 入口见 [test-installer-iso-vm.py](../scripts/tests/test-installer-iso-vm.py) 和 [test-installer-components-vm.py](../scripts/tests/test-installer-components-vm.py)。使用本轮冻结的 ISO、combined image 和一次性工作目录。`--static-only` 只能作为静态证据，启动到菜单也不能替代离线安装后首次启动。最终交付须附至少一份“用户态确实更新、内核仍为 85”的事务明细，以及一份“真实内核变更产生新代”的对照明细。生产预检约束见 [publication-readiness.md](publication-readiness.md)，现有客户端和回退结构见 [kernel-upgrade.md](kernel-upgrade.md)。
