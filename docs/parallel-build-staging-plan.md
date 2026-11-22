# 并行构建、staging 和打包修复计划

适用于这个 checkout 的 x86/64、glibc、APK、merged-/usr 和分代内核。以相同配置和顶层 `-j16` 验收。精确依赖决定作业何时开始。包私有目录中的配置、编译、strip 和压包可以重叠。只在读取共享快照或提交同一个资源时协调访问。

**给接手实施的 agent，2026-11-22。** 实施范围包括下面的 **20 条原始清单（P0 九条、P1 九条、P2 两条）和 4 个补充验收用例**。最后一项 bundle 缓存以测得收益为启用条件。交接时主树 HEAD 为 `8dc5cd8806`，原计划文档提交为 `61be1d9222`。实现仍在独立工作树打样，整机与并行性能验收待执行。

先阅读根目录 [AGENTS.md](../AGENTS.md) 和 [CLAUDE.md](../CLAUDE.md)。实施及故障注入使用独立树。主树的 `.config`、Qt/KF6 开发改动、独立 feeds、overlay、现有签名材料及在途构建均需保留。诊断用的临时配置、测试签名与计时日志放在验证环境内。交付终点为本地 build-only 和产物核验；发布、安装到路由器、刷机与重启另行授权。

## 修复清单

“复现”表示临时目录内的定向实验。它能证明规则有缺陷，不能单独确定历史整机构建失败的原因。“审查”表示有具体代码路径，需用所列用例验证；“条件”表示仅适用于相应配置或输入。

| 优先级 | 位置和证据 | 修复与验收 |
| --- | --- | --- |
| P0 | `package-pack.mk`、`elf-abi.py`。复现并发复制时读到空 JSON；提供者删除私有库后，旧记录及库仍能满足扫描。 | 锁住读取记录和所引用 staging 文件的完整快照。写者按所有者提交文件、链接及清单，最后提交 stamp；测试升级、移除、失败重试、两个并发读者。兼容已有 staging，保留内容相同的共同所有者，实际用例 xfs-admin 和 xfs-fsck。 |
| P0 | `package.mk` 的 InstallDev 在 configure 和锁外删除旧文件，复制前已替换清单。已有开发包清单共享路径。 | 保留旧开发文件至新版本准备完成。仅同一 sysroot 提交及 clean 走同一套规则；私有准备、无关消费者继续并行。覆盖符号链接、空目录、旧清单、失败复制和重试。 |
| P0 | APK 和 .provides 共享独立多目标配方，控制变量只在 APK 目标导出。复现缺 .provides 触发重新打包、过期 ADIR 脚本进入新 APK。 | 每个包/变体一个产物生产者，拆开暂存与最终包的 ELF 输出；每次使用干净控制目录。成功后清理过期版本。用仅请求 .provides、前次失败、删除脚本和相反目标顺序验证。 |
| P0 | `elf-abi.py` 使用无序集合传播 RPATH。在同一输入上改变 PYTHONHASHSEED 可选择不同私有提供者。 | 保持 loader 搜索顺序，根据调用链处理继承。冲突要可诊断，支持合法同内容共同所有者。以多种进程种子和记录枚举顺序检查相同的依赖。 |
| P0 | `.version`、`.sonames` 没有表达私有依赖精确版本。兄弟包提前求值复现冷态无 ABI 后缀、热态带后缀；ncurses-utils 在 libncurses 前注册。wget-any 有多个已选提供者。 | 在提供者注册并就绪后解析 ABI，按实际提供者记录精确版本；私有版本只变时触发消费者重打包，公共 ABI 变化才按需重编译。检查删除或增加别名、去除 ABI 后缀、多个虚拟提供者及循环依赖。 |
| P0 | `scan.mk` 在 DUMP 失败后仍提交 Source-Makefile 空片段。元数据直接写最终文件。复现 conf 退出 9 仍生成 .config-check。 | 成功后原子替换片段、合并结果、Kconfig 输入和依赖图。保留首个失败的 stderr 与退出状态；仅真实配置过期时发出原有提示。失败后重试应恢复。 |
| P0 | `package/Makefile` 用 ln 忽略同名包冲突；复现 adbdump 失败留下空 index.json，下一次 index 跳过。 | 区分同名同内容与不同内容。验证 APK 索引与 JSON 后提交，旧索引可用，缺失/损坏可恢复；测试包增加、移除、内容更新、签名及失败。 |
| P0 | `scripts/download.pl` 复现两个进程争用同一 .hash、哈希不符时删除原档。VCS/vendor 与主档命名范围不同。秒级 stat 缓存可错过覆盖。 | 按实际共享下载目录及目标文件加锁，使用目标文件系统内的私有临时文件，验证完成再改名。覆盖散列不符、写满、失败重试、共享 DL_DIR 的两个 checkout、同 SUBDIR 的不同源和 vendor；不同文件可同时下载。缓存键含设备、inode、纳秒时间和大小。 |
| P0 | `rstrip.sh` 对真实 ELF 使用失败的 strip 仍返回成功；clean-package.sh 忽略移除失败。 | 保留工具原始失败，区分普通 ELF、静态文件、可重定位模块以及正常的非空共享目录；失败不得提交包或 stamp。 |
| P1 | 发布脚本锁位于可被 dirclean 移除的 tmp，普通 make 绕过；临时测试可同时获得两个排他锁。 | 稳定 checkout 锁覆盖互斥的顶层写入口，向递归 make 和 wrapper 传递并验证持锁身份。同一顶层内部照常并行。不同 checkout 保持独立，共享 DL_DIR 或显式共用输出目录按真实资源协调。 |
| P1 | Ninja 1.13 在复现中服从 FIFO jobserver；pipe 作业池顶层 -j2 时子任务峰值为 8；通用入口忽略显式包串行选项。 | 对有效 FIFO 使用 jobserver，兼容旧 make 的 pipe；仅对应的子构建遵守 target 或 host 的显式选项，同时验证两个其他包仍能重叠。 |
| P1 | `host-build.mk` 删除已安装的工具却保留 stamp 后，实测 host-compile 成功且工具仍缺失。顶层 BUILD_VARIANT 可泄漏到 WeeChat 的依赖。 | 为用到的 host 工具声明关键输出，缺失时定向补装，可执行文件原子替换。补齐直接入口所需的 apk、openssl、ninja、pkgconf 等提供者边。限定变体作用域，依赖使用自己的选中变体。 |
| P1 | `kernel-defaults.mk` 的 modules/image 快速路径把生成文件当输入；复现交替执行四次。仅比较 vmlinux.debug 会漏掉已删除或变化的 bzImage。 | 以 kbuild 的真实依赖和必需输出判定就绪，分别验证 debug、ELF、启动镜像、压缩及 stub，保留 objcopy 错误。连续三次热构建核对实际调用和时长。 |
| P1 | `kernel.mk` 将 .ko 依赖挂在旧 IPKG 名称。实测 .ko 改动没有重打实际 APK。bundle stage 是打包副作用，旧目录先被替换，再补 bzImage 等文件。 | 实际包和 staging 依赖 .ko、builtin/config、内核及头文件输入。准备并验证完整 release 再切换。测试只删 stage、选中但 builtin/空的包、混合 release 及中途失败。 |
| P1 | 外部模块读取 flat *.symvers，且追加到固定临时文件。 | 按 generation 和 provider/variant 隔离；只导入声明的依赖，并原子更新完整文件。以 mac80211、button-hotplug 及 CRC 变更验证。 |
| P1 | rootfs 对 overlay 内容连续拼接。复现 a=A,b=BC 和 a=AB,b=C 命中同一键；cache hit 只检查 key。 | 对每条路径、类型、权限、链接、单文件内容建立有边界的输入摘要。包括信任公钥、安装后处理及工具；启用 mklibs 时覆盖其输入或绕开缓存。验证 root/root.orig 成对存在，缺失时重建。 |
| P1 | x86 ISO 快速路径遗漏 installer-components 策略、APK 索引、安装清单和引导输入；可选与必需输出错误处理混用。 | 追踪实际媒体输入，成功提交前核验本配置要求的镜像与 ISO。用单独更改组件策略、引导文件、删除目标和失败复制验证。 |
| P1 | 本机保留多个内核 APK 代际。隔离 apk add 实验中预期 r81 仍选到了仓库里的 r82。 | rootfs 与 installer 使用同次构建的内核及模块集合，核对已装 release、bzImage、headers、所选模块及摘要；安装完成后的滚动升级跟踪关系保持兼容。 |
| P2 | 结构审查：暂存及清单使用 recipe basename；当前 .packageinfo 未发现同名 recipe。显式共享 configure cache 的一个 key 会删除其他 key。 | 用两个同名不同来源及多变体测试，设计兼容旧清单的名称映射；为显式共享 cache 隔离 checkout 与变体，并去掉跨 key 清理。 |
| P2 | kernel-bundle 是 FORCE 目标，在比较结果前会复制、压包、签名。 | 在每个分代输入清单齐备后测量，确认有收益才引入缓存。命中也须验证内容和身份，保留已发布 APK 身份不可变约束。 |

## 四个补充验收用例

前两个用例暴露了独立工作树**草稿**的迁移缺陷，后两个用例直接抽取了**主树现行 Make 规则**。四项都在临时目录复现过，接手时应固化成回归测试。

| 输入与触发方法 | 已观察到的结果 | 修复后的判据 |
| --- | --- | --- |
| 旧 staging 没有新所有权清单。用 `xfs-admin`、`xfs-fsck` 两份旧 ELF 记录声明相同的 `/usr/sbin/xfs_db`，让前者提交不同内容 | 草稿返回 0 并覆盖文件，后者的记录仍然存在。这两个包在本机配置中都已选中 | 首次变更前一次性导入可确认的旧所有者。相同内容、类型、权限和链接目标允许共存；冲突应报告路径和双方包名并保留旧文件。移除任一所有者后，另一包的文件仍可读 |
| 旧记录 `example6.elf.json` 独占 `/usr/lib/old.so`，同一 recipe 的新包使用 ABI 后缀 7 且不再安装旧库 | 草稿按新名查找旧记录，返回 0，旧记录和库均留在 staging | 用稳定的 recipe、变体和二进制包基名关联前次提交。清除旧 ABI 的独占文件、元数据和别名。另测去掉后缀、ABI 不变但删除或新增别名，以及手工移除别名后的定向恢复 |
| 将一个存在、一个缺失的 `.install` 传给实际 `APK_INSTALL_ARGS`，运行 `make -j16` | 返回 0，stderr 为空，只保留存在清单中的包；镜像可以在少包时继续生成 | 从配置和包注册信息**独立计算期望集合**，与本次 `.install`、rolling 片段、实际 APK 对账。区分 `=y`、`=m`、host-only、合法无镜像输出及合法空 APK。应有清单缺失时定向重建生产者，仍缺则阻止 rootfs/ISO 成功 |
| 从 `include/package.mk` 提取 `find_library_dependency_names`，构造 `p0 → p1 → … → p8` | 实际宏只返回 `p1 … p6` | 用带已访问集合的依赖图遍历取代固定展开层数，按实际选中的提供者求解。验证长链、菱形和循环，并记录消费者究竟只需重打包还是需要重编译 |

## 工作树交接与实验边界

- **现有草稿**在本机 `/srv/openwrt-validation/openwrt-parallel-draft`，基于 `687fab97f0`，与主树有版本差。先在主树运行 `git worktree list`，再在草稿树运行 `git status --short` 和 `git diff`。两个新文件 `scripts/stage-package.py`、`scripts/cached-download.py` 在交接时未跟踪，普通 `git diff` 不显示其内容。草稿还涉及 package、download、scan、toplevel、kernel 的 Make 规则及 ELF、strip、依赖提取脚本。按子系统移植有验证的改动，避免从旧树整目录覆盖主树。
- **可复用的部分**包括共享读锁的放置、将 staging 和最终打包的 ELF 输出分开、私有下载候选文件，以及提交前准备清单的思路。草稿的读者遇到 `.stage-pending` 会退出，旧所有者迁移也有上述两个已复现缺陷。实施时增加读写入口共用的恢复步骤，正常重试须自动完成恢复。排序记录能固定遍历次序，私有 RPATH 仍需按真实调用链验证。
- **规模与热点**。上轮实测 424 份开发清单、983 份 runtime ELF 记录；交接复核时分别为 424 和 984。早期扫描还发现 53 个原始开发清单路径重叠，其中含历史清单。第一次迁移建立按路径查询的索引，之后随包提交增量更新；锁内只处理本包触及的路径。用当前配置和构建输出筛选真实冲突。当前扫描未发现活跃 recipe basename 重名，这一项使用专门构造的同名用例验收。
- **已掌握的测试基线**。前轮 23 项 ELF 测试在提供 host `cc`、staged `apk` 和独立测试签名材料后通过。在空工作树可出现 `OK (skipped=23)`，记录实际执行数。上述结果只覆盖当时的 ELF 测试。历史 `-j16` 日志有过 ELF JSON 解析失败，也有只留下 `kernel/linux` 或 `luci-lib-ip` 目标名的失败；后两者的首个错误没有被保留下来。历史热构建曾重新链接内核；相关耗时和 WeeChat 变体案例见[增量构建验证](incremental-build-acceleration-validation.md)和[变体与 Kconfig 验证](scheduled-kconfig-validation.md)。

## 可重复利用的故障实验

从仓库根目录运行下面的探针可重放两个 Make 问题。它们从当前树读取规则，各自在临时目录运行，不依赖已填满的 staging。下面记录的是修复前表现；修复改变宏结构后，应改为测试正式入口的行为。

```sh
python3 - <<'PY'
from pathlib import Path
from subprocess import run
from tempfile import TemporaryDirectory

def probe(directory, makefile):
    result = run(["make", "-rRsf", "-", "-j16"], cwd=directory,
                 input=makefile, text=True, capture_output=True)
    print("exit", result.returncode, "stdout", repr(result.stdout), "stderr", repr(result.stderr))

source = Path("include/package.mk").read_text()
closure = source.split("find_library_dependency_names =", 1)[1].split("find_library_dependencies =", 1)[0]
with TemporaryDirectory() as tmp:
    chain = "".join(f"Package/p{i}/depends := p{i+1}\n" for i in range(8))
    probe(tmp, chain + "find_library_dependency_names =" + closure
          + "\nall:\n\t@echo $(call find_library_dependency_names,p0)\n")

source = Path("package/Makefile").read_text()
args = source.split("APK_INSTALL_ARGS =", 1)[1].split("define apk_install_rootfs", 1)[0]
with TemporaryDirectory() as tmp:
    directory = Path(tmp)
    (directory / "present.install").write_text("present\n")
    for name in ("base-files", "libc", "kernel"):
        (directory / (name + ".version")).write_text("1\n")
    probe(tmp, "STAGING_DIR:=.\nPACKAGE_INSTALL_FILES:=present.install missing.install\n"
          + "APK_INSTALL_ARGS =" + args + '\nall:\n\t@echo "$(APK_INSTALL_ARGS)"\n')
PY
```

| 故障实验 | 修复前证据与验证方法 |
| --- | --- |
| ELF 读写交错与残留 | 在写者截断目标后、复制完成前用同步点放行读者，可触发空 JSON 解析。用 `cc -shared -nostdlib` 做小型私有库，提供者第二版删库，遗留记录仍会给消费者生成 `provider=1-r1`。清除陈旧数据后原扫描能报缺库。修复后同时跑两个读者，验证两者各自获得完整快照 |
| 加载顺序及版本传播 | 两个私有目录提供同一 SONAME，`PYTHONHASHSEED=1` 与 `2` 曾得到不同 pin。颠倒记录枚举次序也要验证。只把私有提供者从 r1 升到 r2，公共 SONAME 不变，检查消费者的精确依赖；用 `ncurses-utils` 先于 `libncurses` 注册的真实顺序对比冷、热 APK。用 `wget-ssl` 和 `uclient-fetch` 检查同一个 `wget-any` 别名不会由最后写入者决定 |
| 假成功与旧产物 | 在 ADIR 预置已从 recipe 删除的 `postinst-pkg`，实际打包曾将它带入 APK。单独请求缺失的 `.provides` 也会重写 APK。另用返回 9 的 `conf`、失败的 DUMP、失败的 `apk adbdump`、对复制的真实 ELF 设置 `READELF=/bin/false` 或 `STRIP=false`。检查首次错误、旧成功结果、stamp 及原命令重试四项 |
| 跨进程下载与锁 | 两个实际 `download.pl` 同时校验同一缓存文件，在第一个哈希进程暂停时让第二个先完成，可触发 `Could not generate file hash`。同名不同预期哈希还可能删除原缓存。另在临时目录持有旧 checkout 锁，删除并重建锁所在目录，可在新 inode 再次取得排他锁。分别验证相同资源互斥、不同文件或不同 checkout 的独立资源能重叠 |
| 并发预算与 host 输出 | GNU Make 4.4.1、Ninja 1.13.2 下，顶层 `-j2` 用 FIFO 的子任务峰值为 2，使用 pipe 的原规则曾达到 8。用可计数的子任务验证，两组无关包要有重叠。另在临时 host prefix 删除工具但保留 `.built`、`_installed`，原 `host-compile` 返回成功却没有补装 |
| 内核、rootfs 与 ISO | 依次只动 `.ko`、删除输出 `bzImage`、只改引导或 installer 组件策略。overlay 中 `a=A,b=BC` 和 `a=AB,b=C` 曾产生相同 rootfs 键。用临时 APK 仓库放入 r81/r82 两套内核，原安装参数会选 r82；构建 r81 的镜像须装入 r81，后续设备 world 仍可滚动升级 |

## 集成顺序和验收

1. 先修能吞掉首个错误、破坏上次成功输出的路径，并保留故障注入用例。用只读快照记录现有配置、已选变体和基准构建参数。
2. 完成 runtime staging 和 InstallDev 所有权迁移，连接 ELF、提供者、兄弟包与打包依赖。用不完整 staging 的冷态与已有清单的热态分别试验；核对包内容、元数据和真实路径。
3. 修复下载、host、调度及顶层互斥，再连接内核、rootfs 和安装媒体的真实产物。共享锁等待和临界区时长分别计量，不能将整个编译或整个打包放入写锁。
4. 以同一配置、同一初始状态和原并行度运行定向包、冷构建、连续三次热构建和一次故障恢复。记录 `BUILD_LOG=1 V=s`、各阶段时间、独立包的重叠、产物摘要、首个错误及锁等待。分别报告夹具、真实包、整机 build-only 的结果。整机成功需验证本次 APK、内核、rootfs 和 ISO 一致；发布、刷机和设备重启另行授权。

### 实施时的关键约束

- **锁与事务。** 分别定义 runtime staging、开发 sysroot、checkout 和共享下载目录的锁。只读 ELF 阶段在锁下取得记录和所引用文件的一致视图，随后释放读锁再计算依赖。开发 sysroot 的消费者通过实际提供者的完成目标建立顺序。复制、散列、strip、压包及冲突候选准备尽量在包的私有目录完成，提交时复核所有权。清单和 stamp 在产物就绪后更新。测试在替换文件后、提交清单前杀死写者，以及恢复过程再次被中断；新的读者或同一个构建命令应能进入恢复流程。对于旧记录无法证明归属的文件，在隔离目录从已选包的私有产物重建相应 staging，再切换到验证过的结果。
- **启动与递归。** `rules.mk` 中 staged `flock` 缺失时的 `locked=$(1)` 会跳过互斥，冷入口也须获得有效锁。普通顶层 make、`build-and-publish.py`、`update-mainline-kernel.py` 和已有的 `scheduled-maintenance.py` 入口遵守同一持锁约定；检查继承 fd、递归 make、dirclean、两个 checkout 共用 `CONFIG_BINARY_FOLDER` 的情况。下载包装器与 `download.pl` 对同一文件避免重复获取同一把锁；缓存命中需核对哈希前后文件身份，保留设备、inode、大小、纳秒 mtime 与 ctime，避免每次解析 Makefile 都重新读取大档案。
- **依赖与打包。** 同一源码的多个二进制包要覆盖正向和反向注册顺序、虚拟提供者及 `.packageauxvars` 的重复项。公共库按 SONAME，私有库按实际可达的、精确版本的提供者；按调用对象区分 DT_RPATH 继承和 DT_RUNPATH 的直接搜索。仅工具链运行库的 bootstrap 可读取限定的 toolchain sysroot。保留原有包内 `.NOTPARALLEL`，直到单一生产者、所有入口的导出变量及缺任一输出的恢复都已通过。多个独立包在整个阶段继续并发。打包内的 `readelf`、kmod `objcopy` 与 strip 任一真正失败都要返回失败，保留静态 ELF、合法空结果、文件权限和包本身的 strip 选项。
- **包集合与包身份。** `read_apk_inventory()` 会核对收到的片段和文件，自身只要求集合非空；缺了某一份片段仍需拿独立期望集合检测。区分 rootfs 安装集合与 rolling 构建集合，后者还可能含按现有策略补建的历史迁移包。合并的 ADB、JSON、rootfs、ISO 使用该次构建已验证的集合。现有 `apk mkpkg/mkndx` 已有单输出提交机制，修复集中在上层多文件一致性。若修复确实改变已发布 APK 字节，使用已有 release 分配及发布前不可变身份校验；在报告中列出受影响包及其原因。
- **内核及媒体。** `modules` 与 `image` 分开验证实际输入和必需输出，防止内核树生成文件反复使另一目标过期。将依赖挂到 `PACK_kmod-*` 和对应 staging 目标，同时覆盖模块删除、内建和合法空包。镜像、模块、headers 和符号表须属于同一 release。保留内核签名、压缩和 generation 分配规则。镜像和 ISO 的必需复制操作应传回错误，缓存标记在所有要求产物校验后才生成。启用 `mklibs` 的配置在其输入尚未覆盖时绕过 rootfs 缓存。

### 真实包和整机通过标准

| 用例 | 要留存的证据 |
| --- | --- |
| `ncurses-utils/libncurses`、`gnome-shell/mutter`、`wget-any` 两个提供者、`libzip` 及其虚拟依赖消费者 | 相反注册顺序、冷/热 staging 得到相同 APK 依赖；私有 release 变化时消费者重新打包次数和实际编译次数；普通包不能借用未选中的历史提供者 |
| `xfs-admin/xfs-fsck`，Qt/KF6 和 WeeChat | 后安装、卸载及失败重试均保住共同文件；删除已安装的 Qt 代码生成工具后，由其生产者补装；直接包入口具备需要的 apk、openssl、ninja、pkgconf 等工具；指定 WeeChat 变体不会传给依赖 |
| 外部模块、kernel bundle、rootfs/ISO | 用 mac80211、button-hotplug 或当前已选对应模块验证 CRC 变更、丢失 stage、builtin 和空包。比对镜像内 kernel release、模块清单、headers 包和实际启动镜像摘要。删除 `root.orig`、改变文件内容边界或只改 installer 策略时能恢复或刷新对应产物 |
| 并发和耗时 | 在相同配置、工具版本、缓存起点及负载下，记录变更前后一次冷构建、至少三次连续热构建和一次故障重试的总耗时。提供两个无关包编译/压包区间的实际交叠、锁持有及等待时长、触发重编译的具体目标。**热构建耗时中位数回退超过 5% 时，定位开销并复核后再验收。** 记录首次所有权索引迁移耗时，单独列出稳态结果 |

在准备好的**隔离构建树**内，现有回归入口包括以下命令。针对上面的故障点补齐定向用例，尤其要验证正式 make 目标。测试签名用该验证树自己的临时材料。

```sh
python3 scripts/tests/test-elf-abi.py
python3 scripts/tests/test-ucode-abi.py
python3 scripts/tests/test-package-metadata-kconfig.py
python3 scripts/tests/test-kernel-build-inputs.py
python3 scripts/tests/test-kernel-bundle.py
python3 scripts/tests/test-kernel-apk-policy.py
python3 scripts/tests/test-build-and-publish.py
python3 scripts/tests/test-mainline-kernel-updates.py
git diff --check
```

完成定向包和故障恢复验证后，在隔离树依次跑 rolling 和完整 build-only。以下示例为两次运行生成独立的计时文件，重复测量时重新创建 `timing_dir`。先核对隔离树的配置、feeds 和分代状态；包装器会执行现有的内核 generation 预留逻辑。

```sh
timing_dir=$(mktemp -d)
BUILD_LOG=1 BUILD_TIME_LOG="$timing_dir/rolling.tsv" python3 scripts/build-and-publish.py build-only --rolling -j16 V=s
BUILD_LOG=1 BUILD_TIME_LOG="$timing_dir/full.tsv" python3 scripts/build-and-publish.py build-only -j16 V=s
```

交付记录附本次源码与 feed 版本、配置摘要、各项命令及退出状态、跳过项、并行时间线、APK 身份和镜像核验结果。将既有基线失败与此次新增回归分别列出。build-only 的证据覆盖主机构建及产物；设备部署和实际启动结果应有各自的验证记录。
