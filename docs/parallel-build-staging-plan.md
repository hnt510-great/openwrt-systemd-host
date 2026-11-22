# 并行构建、staging 和打包修复计划

适用于这个 checkout 的 x86/64、glibc、APK、merged-/usr 和分代内核。以相同配置和顶层 `-j16` 验收。精确依赖决定作业何时开始。包私有目录中的配置、编译、strip 和压包可以重叠。只在读取共享快照或提交同一个资源时协调访问。

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

## 集成顺序和验收

1. 先修能吞掉首个错误、破坏上次成功输出的路径，并保留故障注入用例。用只读快照记录现有配置、已选变体和基准构建参数。
2. 完成 runtime staging 和 InstallDev 所有权迁移，连接 ELF、提供者、兄弟包与打包依赖。用不完整 staging 的冷态与已有清单的热态分别试验；核对包内容、元数据和真实路径。
3. 修复下载、host、调度及顶层互斥，再连接内核、rootfs 和安装媒体的真实产物。共享锁等待和临界区时长分别计量，不能将整个编译或整个打包放入写锁。
4. 以同一配置、同一初始状态和原并行度运行定向包、冷构建、连续三次热构建和一次故障恢复。记录 `BUILD_LOG=1 V=s`、各阶段时间、独立包的重叠、产物摘要、首个错误及锁等待。分别报告夹具、真实包、整机 build-only 的结果。整机成功需验证本次 APK、内核、rootfs 和 ISO 一致；发布、刷机和设备重启另行授权。
