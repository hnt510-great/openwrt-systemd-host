# 同版本 APK 重建诊断与 release 分配实施交接

**状态：一期与二期（2a 类型 ABI 证据、2b 构建输入追踪与隔离冷复建）均已实施并通过主机与签名 feed 回归验证。** 审查日期为 2026-11-22，工作目录为 `/srv/openwrt`，基线提交为 `cc528983a9d7a2e6ed94839401b7906f78b34a0d`。本文第 2、3 节记录基线实测和代码行为，第 4 至 7 节规定分期实现及验收。

## 1. 交接目标、分期范围与第一步

目标是在已发布的包名、版本、架构对应的 APK 字节发生变化时，让工具说明**哪里变了、能证明到什么程度、可执行哪个发布动作**。维护者应能凭具体证据复核少数例外，日常无需手改 release 账本。一个 SONAME 可以保持多年，其间既可能有无害的实现调整，也可能出现函数参数或公开结构布局变化；分配了新 release 也仍需验证旧消费者能否升级。

维护者已选定分期与策略：

1. **分期范围**：
   - **一期（当前实施，纯发布与诊断工具链改造，不侵入 OpenWrt 构建规则）**：包含原阶段 A（1–3 项）、阶段 C、阶段 D。报告 schema 预留 `type_abi`、`build_provenance`、`reproducibility` 字段，一期显式标记为 `not_collected`。
   - **二期（后续扩展，涉及构建侧证据与隔离复建）**：包含 **2a**（原阶段 A 第 4 项：公共库包外 DWARF/ABI 描述与固定版本 `libabigail`/`abidiff`）与 **2b**（原阶段 B：构建输入追踪、单次隔离冷复建、可复现性证据与漂移取证）。
2. **写账前复核策略**：公共库加载顺序变化、缺少类型证据，以及**一期中**无对外 ABI 的可执行文件仅实现字节变化（如 `resources`），均给出完整诊断报告与建议 release 号，**写账前复核**（保守策略；待二期补齐冷复建/类型证据后再开放对应自动分配）。
3. **纯封装差异复用旧包**：两个可信签名 APK 仅外层压缩不同、完整解压 ADB 流相同，滚动发布**选用已发布原包**。在冻结清单前完成选择，并记录原候选和所选文件的摘要。
4. **二期隔离冷复建策略**：二期接入后，有机会自动分配但实现变化成因未明的冲突，每个候选涉及的源 recipe **最多隔离冷复建一次**；复现候选才继续，再次出现有效载荷漂移时停止分配并留下定位材料。**默认禁止大型/高成本 recipe（如 Qt、LLVM、Rust/Cargo、Mesa、WebKit、QEMU 等）自动冷复建**：除非显式授权（`--allow-high-cost-cold-rebuild` 或 `--authorize-cold-recipe`），否则直接跳过冷复建并生成带输入摘要与诊断证据的人工复核报告。

**接手后的第一批改动**应是诊断器和分配器的失败用例。先用测试复现“普通文本变化掩盖未知 ELF 差异”“依赖重排被排序抹平”“带日期的配置值变化被判良性”。在临时签名 feed 中证明决策正确后，再接入协调器的写账与重试。开始前检查 `git status --short` 和 `git diff -- configs/apk-elf-rebuilds.mk`，核对本节基线与第 3 节的四个摘要。

审查时唯一跟踪文件改动为 [release 账本](../configs/apk-elf-rebuilds.mk)。两个 recipe 的 `PKG_RELEASE` 均为 1，工作树已经把 `librsvg 2.62.4-r1` 的有效输出从 r5 改到 r6，把 `resources 1.10.2-r1` 的有效输出从 r2 改到 r3，各自的 `ELF_DEP_` 同步更新。保留工作树现状，回放案例用临时账本。后续补审这两项时沿用已分配的号码。

## 2. 当前系统怎样处理一次冲突

| 环节 | 现有实现与实施入口 |
|---|---|
| 触发重建 | 两个 recipe 都包含 `gnome-rust.mk`，该文件自身列在 `PKG_FILE_DEPENDS` 中。提交 `1a95ddc477` 将其安装步骤由 `$(NINJA)` 改为 `$(NINJA_TARGET)`。`git show 1a95ddc477 -- include/gnome-rust.mk rules.mk` 可同时查看调用点与 jobserver 规则。这能解释重新执行构建的原因，单靠提交记录无法定位哪次链接产生了差异。[GNOME Rust 规则](../include/gnome-rust.mk) |
| 应用版本与构造 APK | `BuildPackage` 在应用 `ELF_REBUILD_` 前调用 `CheckElfRebuildVersion` 检查预留版本。`package-pack.mk` 处理精确依赖、执行 `RSTRIP`、生成包内 ELF 信息并打包。保留这些规则和既有依赖 stamp；把主机诊断元数据放入每个 APK 会再次批量改变已发布内容。[版本映射](../include/package.mk) · [单生产者打包](../include/package-pack.mk) |
| 检出冲突 | LAN 发布器以目标 ABI 的已发布快照为基线，比较仓库路径与 APK SHA-256，生成签名索引，对最新候选和保留包做相应检查。在该路径通过 ELF/ucode 审计后，遇到同版本不同摘要会抛出 `SameVersionRebuildError`。`same_version_rebuild_error()` 诊断所有冲突，终端只展开前 8 项；一份自定义包可能同时出现在来源仓库及 `custom/` 投影。[发布器](../scripts/publish-lan-apk-feeds.py) |
| 诊断 | `compare_metadata()` 比较部分 ADB 字段，按文件摘要定位差异。`analyze_elf()` 主要按节名、长度和字节区间比较，普通机器码、GOT 和重定位变化通常成为 `unknown`。无节表 ELF 不能走这条节比较路径。`elf-abi.py` 的包内契约适于计算依赖能力，但其 `needed` 用集合去重、排序，已丢失原始加载顺序。[差异诊断](../scripts/diagnose-apk-rebuild.py) · [现有 ELF 契约](../scripts/elf-abi.py) |
| 选 release | `classify()` 读取诊断 verdict，并比较两份 APK 的 `so:` 依赖。`eligible()` 接受 `change` 或 `so_changed`，独立 CLI 还支持人工 `--accept-unknown`。`plan()` 结合 `tmp/.packageinfo`、账本、构建产物和历史快照选号，已有 ABI 后缀、LuCI 占位版本和运行时派生版本的处理。`apply()` 最后直接 `write_text()` 写账。[分配器](../scripts/allocate-rebuild-releases.py) |
| 重建与发布 | `publish_allocating()` 最多进行三轮分配以处理级联；普通路径定向编译，rolling 路径重跑包图并刷新期望清单。`project()`、`validate_expected_apks()`、冻结 bundle 哈希和发布回执共同约束最终文件。生产协调器还会核对路由器基线、执行升级模拟、复查准备好的快照，再切换别名。[协调器](../scripts/build-and-publish.py) · [升级预检与 authorize](../scripts/apk-upgrade-preflight.py) |

### 已确认的错误判定和入口差异

- **混合差异会被放行。** 给同一 `Report` 加一个 ELF `unknown` 和一个文档 `change`，现有 `Report.verdict` 为 `change`，`eligible()` 返回真。独立构造 `unknown + so_changed=True`，结果也为真。新决策须遍历完整发现列表，保留每个未决项。
- **日期匹配范围过宽。** 把一行 `allow=0 # built on 2026-01-01` 改成 `allow=1 # built on 2026-02-01`，现有文本规则给出 `benign`。可限制终端 diff 的行数，决策必须检查全部变化。ZIP 的条目名集合和解压数据相同，也不足以涵盖权限、重复条目等语义。
- **ADB 顶层语义有遗漏。** 单改顶层 `triggers`，`compare_metadata()` 返回空 findings 和空路径列表。此次检查的 apk-tools 3.0.5 包 schema 还包含顶层 `replaces-priority`。只有这些变化时可能落入“签名或封装”提示，混合其他变化时则可能漏报。
- **独立诊断与生产证据的来源不同。** 现有诊断提取使用 `--allow-untrusted`；生产发布器另有签名门禁。独立 CLI 的 `resolve()` 选择配置目标下按名称排序的最后一份快照；分配 CLI 的 `--destination` 只传给选号步骤。实施时从一次已验证的比较生成报告，显式传入目标、基线快照及两份实际文件，避免从不同目标取证和选号。
- **两个 dry-run 入口行为有差异。** build 入口会拒绝 rolling dry-run 与自动分配组合。独立 publish 入口把 `args.dry_run` 传给发布函数，同时仍将 `args.allocate_rebuilds` 传给外层重试；一旦捕获冲突可进入写账与 make。这个结论来自控制流检查。回归测试应在临时目录触发冲突，检查账本、make 调用次数及快照别名。

下面的只读探针可直接改成阶段 A 的单元测试。在审查基线上，前两行均以 `True` 结尾，第三行是 `([], [])`，最后一行是 `benign`。新实现的验收看“允许哪个动作”和“保留哪些未决项”，旧 verdict 字段可继续兼容。

```python
# 在仓库根目录，用 python3 -B 运行。
import importlib.util
from pathlib import Path

source = Path("scripts/allocate-rebuild-releases.py")
spec = importlib.util.spec_from_file_location("rebuild_probe", source)
allocator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(allocator)
diagnose = allocator.DIAGNOSE
report = diagnose.Report("old", "new", findings=[
    diagnose.Finding(diagnose.UNKNOWN, "usr/lib/libsample.so [.text]", "bytes differ"),
    diagnose.Finding(diagnose.CHANGE, "usr/share/doc/sample", "text content changed"),
])
print(report.verdict, allocator.eligible({"verdict": report.verdict, "so_changed": False}))
print(allocator.eligible({"verdict": "unknown", "so_changed": True}))
print(diagnose.compare_metadata({"triggers": ["/old/*"]}, {"triggers": ["/new/*"]}))
print(diagnose.analyze_content("etc/settings",
    b"allow=0 # built on 2026-01-01\n", b"allow=1 # built on 2026-02-01\n")[0].verdict)
```

## 3. 两个真实案例与证据边界

已发布基线固定为 `/srv/openwrt-feeds/public/snapshots/20261122T052658.620916Z/base/`。新包取自本仓库 `bin/systemd/packages/x86_64/base/`。四份 APK 均以仓库公钥验证成功。以下比较跨越已分配的 release，适于检验载荷诊断；原始被拒绝的**同版本候选**和当时的完整构建输入未作为此组样本留存。跨版本的 `info.version`、派生哈希和包内清单版本本身就会变化，不能作为原事故发生内容变化的证据。

| 样本 | APK 文件 | 整包 SHA-256 |
|---|---|---|
| 已发布 | `librsvg-2.62.4-r5.apk` | `1314716a2564ca33058393d00064615b5cbf069443f9a417c4b72e8299d40968` |
| 本机构建 | `librsvg-2.62.4-r6.apk` | `7db64267a001dac6672241d847f2b0dfb3ce799f1bc11dda15fc17be11994c49` |
| 已发布 | `resources-1.10.2-r2.apk` | `97a950a6bc3286ce62b7dfb6097f9b5228c25a8f7baf97a36491880a20c2b20c` |
| 本机构建 | `resources-1.10.2-r3.apk` | `c545395178872702f16584bf4e1df79e85af2f563ba637557545d3f7520a88d5` |

### librsvg 应在写账前复核

文件清单没有增删。文件内容摘要变化集中在 `usr/lib/apk/packages/librsvg.elf.json` 和 `usr/lib/librsvg-2.so.2.62.4`。后者两侧均为 4,224,256 字节，SONAME 均为 `librsvg-2.so.2`。两侧都有 55 个已定义的非本地动态符号，此次抽查的符号接口属性一致。GNU 版本需求节的原始字节改变，按库名、版本名、flags 和版本索引展开后相同。

**决定复核的是有序依赖。** 依赖名称集合均为 13 项，只有第 6 至 9 位不同：

| 位置（从 1 开始） | 已发布 r5 | 本机 r6 |
|---|---|---|
| 6 | `libc.so.6` | `libm.so.6` |
| 7 | `ld-linux-x86-64.so.2` | `libc.so.6` |
| 8 | `libgcc_s.so.1` | `ld-linux-x86-64.so.2` |
| 9 | `libm.so.6` | `libgcc_s.so.1` |

ELF 规范赋予 `DT_NEEDED` 的相对顺序含义。顺序变化可能影响符号解析，实际影响取决于提供者和加载环境。本例的 `.dynamic`、`.dynstr`、`.gnu.version_r`、`.got`、`.rela.dyn`、`.relr.dyn`、`.text` 均有变化，其中 `.text` 有 43 个字节不同。公共符号和 SONAME 一致无法排除类型布局变化。报告应给出原始顺序、语义化版本需求、缺失的类型证据和复核理由。[ELF gABI 动态链接规范](https://refspecs.linuxfoundation.org/elf/gabi4%2B/ch5.dynamic.html)

### resources 可进入隔离复建

文件清单同样没有增删。除 `resources.elf.json` 外，有两个文件内容摘要变化：

| ELF | 已观测的变化 |
|---|---|
| `usr/bin/resources`，4,734,480 字节 | `.text` 有 30,402 个字节不同，另有 `.init`、`.got`、`.rela.dyn`、`.data.rel.ro`、`.eh_frame` 和 `.eh_frame_hdr` 变化。 |
| `usr/libexec/resources/resources-processes`，2,553,232 字节 | `.text` 有 4,368 个字节不同，另有 `.got` 和 `.rela.dyn` 变化。 |

两个文件都是可执行文件，ELF 类型为 `ET_DYN`，均无已定义的非本地动态符号。抽查的动态符号属性、有序依赖和 GNU 版本表一致。实施后的预期结论为“应用实现变化，可尝试复建”。最终自动分配还需整包覆盖、加载标志检查和复建结果；GUI、命令行和进程间协议的行为没有在本次检查中验证。

### 工具与纯封装实验

- 当前用户空间配置为 `CONFIG_USE_STRIP=y`、`CONFIG_STRIP_ARGS="--strip-all"`。三个已抽查 ELF 都没有 `.debug_info`。`librsvg` 的 `ipkg-install` 副本仍有 `.symtab`，但已无 `.debug_info`。只在 `RSTRIP` 前复制文件，无法为这次历史构建补出类型信息。
- 主机系统 Python 可导入 `elftools`，本次检查的 staged Python 无法导入；packages feed 的 `python-pyelftools` recipe 已提供 `HostBuild`。主机 PATH 中未发现 `abidiff`、`abidw`。实施时为发布主机显式准备及记录工具版本，避免把本机 Python 环境当作构建前提。
- 已将真实、已签名的 `librsvg r5` 的 `ADBd` 外层 DEFLATE 重新编码。APK 从 1,938,098 字节变为 2,097,704 字节，解压后的完整 ADB 流相同，两个文件均通过原公钥的 `apk verify`。这个实验支持精确定义的“复用旧包”路径。它没有覆盖重签名、改变包内文件 mtime 或其他压缩格式。

## 4. 发布决策与报告接口

报告按四个维度给出结果。同一包允许同时出现多种发现；在报告中保留全部路径和不确定性。

| 维度 | 应记录什么 |
|---|---|
| 包身份与内容 | 目标及基线快照、来源仓库和投影、包名/版本/架构、旧新摘要、信任公钥指纹与验签结果。比较包信息、依赖与提供项、脚本、triggers、替换优先级、文件增删、类型、模式、属主、xattr、链接目标、文件时间和内容。对派生字段注明如何验证；对无法读取或解释的字段保留阻断项。 |
| ELF 与 ABI | 每个变化对象的角色、原始 ELF 摘要、变化的字节/节，以及程序头、加载契约、版本化符号和类型证据的比较结果。标出兼容性判断的覆盖范围，包括所缺证据。 |
| 构建来源与复现 | 记录可验证的输入差异、单次隔离复建的输入与输出摘要、执行结果及未确认的历史成因。分别报告整包字节、完整 ADB 流、有效载荷是否一致。相同输入下复现一次只能支持本次观察。[可复现构建定义](https://reproducible-builds.org/docs/definition/) |
| 发布动作 | 只读报告给出动作、理由、阻断项、建议号和受影响的 recipe/包；记录分析器、策略及证据版本。保留现有 CLI 可读输出、JSON 旧字段及退出码，协调器和分配器以新增的版本化决策字段为准。 |

**动作优先级。** 先验证身份、签名及证据完整性，再检查全部未决项与契约风险，最后评估自动动作。未识别的字段或解析错误必须落在具体路径上。旧 `benign/change/unknown` 仍可用于解释单条发现。

| 条件 | 最终动作 |
|---|---|
| 整包字节一致 | 沿用现有身份；走原有完整性与发布检查。 |
| 整包不同，两侧受同一仓库信任，解压至合法结束后完整 ADB 流逐字节一致 | 在未冻结的滚动候选中选用已发布原包，记录两个 SHA-256 与选择理由。格式不支持或内层流不同则退出此分支。 |
| 无对外 ABI 的可执行文件只有实现字节变化，加载/导入等检查通过，全部包差异有解释 | **一期保守策略：写账前复核**（报告给出无对外 ABI、依赖与加载检查结果及建议号，人工批准后写账）。二期接入隔离冷复建并复现候选后，在 `--allocate-rebuilds` 下自动分配。 |
| 可归因的包内容或元数据修改，或已验证的提供者迁移引起消费者重链接 | 按现有分配能力处理。须解释整包差异，验证新提供者、消费者和精确版本依赖；若同时有未知项，先完成复核。 |
| 公共库实现变化，加载顺序、导入导出及受覆盖的公开类型均通过相应检查 | **一期**因未采集包外类型证据，统一报缺类型证据并走**写账前复核**。二期在类型覆盖、构建来源与复现要求均满足后可自动分配；加载顺序变化、类型证据缺失、插件契约未能识别或其他未知差异始终须写账前复核。 |
| 明确不兼容、签名或身份异常、相同输入复建时有效载荷继续漂移 | 分别转入 ABI 迁移与反向依赖重建、拒绝候选、排查非确定性。禁止靠再加一个 release 或通用复核标记重试通过。 |

## 5. 实施顺序与接口约束

一期依次落地 **阶段 A（一期范围）→ 阶段 C → 阶段 D**；二期再实施 **阶段 2a（类型 ABI 证据）→ 阶段 2b（构建输入追踪与隔离冷复建）**。

### 一期 · 阶段 A：建立只读报告，修复混合判定

1. 从发布器传递已冻结的旧/新文件、签名基线和摘要给比较器。独立诊断命令仍可检查任意两个文件，明确呈现信任状态；写账入口只接受可复验的可信证据。以身份和摘要对去重相同的 `base`/`custom` 发现，保留全部来源路径。同身份出现多个不同候选摘要应列出冲突。
2. 比较完整 APK schema，用程序头和动态表检查可加载 ELF。保留原始 `DT_NEEDED` 顺序与重复项，核对架构、字节序、解释器、有序 RPATH/RUNPATH、段权限、栈/RELRO、加载标志及架构属性。按名称、符号版本及默认版本、定义/未定义、类型、绑定、可见性比较符号；对公开对象/TLS 还比较大小。函数地址和机器码长度作为实现证据记录。检查节表缺失、截断、重名节和未能覆盖的头部差异。
3. 结合 `PT_INTERP`、PIE 标志、SONAME、实际安装位置和包角色判别应用、公共库、私有库和插件。`ET_DYN` 单独不能决定采用哪个策略。Qt/KF 插件、GModule、ucode 模块及 Rust FFI 的外部契约可能在动态符号之外。专用契约和现有 ucode 锁继续生效。
4. 报告 schema 在一期即包含 `type_abi`、`build_provenance`、`reproducibility` 字段，均显式标记为 `not_collected`，保证二期接入无需破坏兼容。

**交付条件**为 `librsvg` 报第 6–9 位 `DT_NEEDED` 换序并在写账前停止，`resources` 报两个无对外 ABI 可执行文件实现变化并在一期按保守策略停止于写账前复核，完整 JSON 保留全部未决项，旧 CLI 的使用者可继续读取结果。此阶段可独立合入并以只读方式观察生产候选。

### 一期 · 阶段 C：原子写账、复核和升号后绑定

1. 保留现有选号算法、当前 recipe 键、ABI 后缀别名、精确依赖及特殊版本解析。遇到公共库或纯可执行文件待审项只给建议号。复核与报告摘要、旧/新 APK 摘要、目标快照、策略版本和维护者理由绑定。独立 CLI 与协调器共享决策，宽泛的 `--accept-unknown` 不得作为生产写账凭据。
2. 计划与应用之间可能发生并发构建或新快照晋级。复用 checkout/发布锁的既有顺序，写入前重读账本、基线、候选及已占用版本。整批满足条件后同目录临时写入、刷盘、原子替换；保留原文件其他修改与历史预留。旧有效号即使从当前映射值消失也应保留预留证据，避免随后被 recipe 复用。预留记录与客户端 world 精确 pin 迁移分别处理。
3. 保存可恢复的分配记录，串联原冲突报告、批准、原/新账本摘要、分配版本和最终制品。写账后重建失败或进程中断，重试应找回同一预留。重建新版本后再次验签、比较载荷，只允许此次升号可解释的包版本、版本化清单、别名和精确依赖等差异。额外 ELF 漂移重新进入诊断；不能因为新文件名已经消除了原冲突就丢掉审核条件。

**交付条件**为同一输入重试只分配一次，人工复核针对准确的字节，崩溃恢复后仍能从最终 APK 回溯原始冲突。

### 一期 · 阶段 D：接入发布和冻结路径

1. 对纯封装差异选择旧包时，先核验两份 APK 和旧快照摘要，记录“本次实际构建摘要”及“最终选择摘要”。在 rolling 期望集合冻结前统一来源仓库及投影的选择；原候选仍必须存在并已核验，不能用快照填补本次漏建的包。索引、预检和晋级复算均使用最终选定文件。冻结 bundle 按原 manifest 验证。
2. 保留普通构建与 rolling 的重建路径差异、三轮级联上限及精确依赖重算。若交付范围包含 rootfs/ISO，分别核对其中的清单和制品。一次包重打的结果只能证明该包产出。
3. 统一入口的预览语义。独立 publish 的 dry-run 遇到冲突时给出计划，账本写入和分配后的 make 调用次数均为零；rolling build dry-run 原有的构建/预检语义另行测试。冻结 bundle 发布继续禁止现场分配和重建。
4. 扩展升级回执绑定诊断器/策略摘要、选择或分配记录和最终 APK SHA-256。在晋级前复核证据、账本、基线和快照。保留签名、保留包的 ELF/ucode 审计、内核通道独立性、实际路由器基线及求解模拟。灰度先输出只读报告，再启用有证据的动作；有回归时可停用新自动动作，沿用已有不可变身份检查。[发布就绪要求](publication-readiness.md) · [滚动构建与冻结制品](incremental-build-acceleration-validation.md)

### 二期 · 阶段 2a：公共库类型 ABI 证据（原阶段 A 第 4 项）

公共库从实际链接过程保留匹配的 DWARF 或 ABI 描述，放在 APK 外。以最终 ELF SHA-256、来源构建和工具参数绑定证据，记录导出接口的类型覆盖。固定 libabigail 版本，显式检查缺少调试信息、解析错误、ABI 变化及不兼容的退出位。仅有 `abidiff` 返回 0 无法证明覆盖。补录旧证据须从精确旧输入重建并匹配已发布 ELF 摘要，否则回到写账前复核。[abidiff 官方手册](https://sourceware.org/libabigail/manual/abidiff.html)

### 二期 · 阶段 2b：采集构建输入，执行一次隔离冷复建（原阶段 B）

1. 按源 recipe、变体和编译目标记录源码/补丁、实际生效的 include、配置、工具链和依赖产物摘要，保留编译、安装、链接的关键参数、链接输入顺序、并行设置及 `SOURCE_DATE_EPOCH`。记录发生于对应构建步骤，最后与 ELF、APK 绑定。输入变化期间产生的结果作废。环境变量用白名单采集，私钥和完整环境转储排除在证据包外。
2. 按 recipe 对冲突合并。复建采用隔离工作目录与私有可写 staging/output，在等价构建路径下固定首次候选的输入、参数和有效 release。该 recipe 从 prepare/compile 起重新执行，绕过已有 `.built`、Cargo incremental、sccache 等结果缓存；已校验的下载和固定依赖可复用。复建不得清理活动 checkout、改写其 staging 或预留内核代际。
3. 先比输入，再比输出。若候选与复建的语义载荷和元数据匹配，记录这一次的复现范围；若仅外层封装不同，单独记录。若载荷漂移，保留两次 ELF、首个差异文件、最终链接命令和有序对象/库列表，排查 Cargo build script 输出、Meson/Ninja 输入枚举、路径映射、时间和并行顺序。避免全局排序链接库，因为这种“修复”可能改变真实加载行为。

**二期交付条件**为一次真实重新编译可与缓存命中区分，稳定样本得到复现记录，漂移样本零写账；无冲突的热构建不触发任何冷复建。

## 6. 验收矩阵

### 一期验收矩阵

| 场景 | 必须观察到的结果 |
|---|---|
| `librsvg` 实物回放 | 报告 `DT_NEEDED` 第 6–9 位换序、缺失类型证据（`type_abi: not_collected`），动作落入写账前复核并停止自动分配。 |
| `resources` 实物回放；无对外 ABI 签名应用夹具 | 实物给出两个变化可执行文件（无对外 ABI、依赖/加载检查通过），一期按保守策略停止于写账前复核并给出建议号；维护者摘要绑定批准后才可写账。 |
| 文本或依赖变化与未知 ELF 混合；仅 triggers、权限、链接目标、日期行配置值变化 | 报告覆盖每一项，任何未决项都能阻止自动分配；这些差异均不得走纯封装复用。 |
| 相同完整 ADB 流用不同外层压缩；无效签名、截断、内层差一字节作负例 | 正例在滚动/发布候选中复用旧 APK，两个摘要和最终索引可核查；负例拒绝复用。 |
| 单包同时投影到两个仓库；ABI 后缀、LuCI 占位版本、私有库精确锁和保留消费者 | 同一冲突只选号一次；不同字节不能被去重；升级模拟可安装所声明的提供者/消费者组合。 |
| 写账前快照前移、两进程选号、写账后 make 失败、中断恢复、重打时 ELF 再变 | 过期决定失效，旧文件/账本可恢复，无重复号；新身份不能绕过对其载荷的检查。 |
| dry-run、缺一个 rolling 期望 APK、bundle 冻结后改字节、晋级前换策略 | 独立 publish dry-run 零写账零 make；后三种各自在已有或新增对应门禁停止。旧快照和公开别名保持可核对。 |

### 二期验收矩阵（后续实施）

| 场景 | 必须观察到的结果 |
|---|---|
| 同 SONAME 的 C/C++ 测试库改变公开参数/结构布局（2a） | 有包外 DWARF/ABI 类型证据时报告 ABI 变化；剥离类型证据后报告覆盖不足并回退写账前复核。 |
| 稳定应用夹具与同输入漂移夹具冷复建（2b） | 稳定夹具冷复建一次后自动分配一个 release；同输入漂移夹具零写账并保留定位材料；无冲突热构建零冷复建。 |

本次审查已运行下列 7 套现有主机测试，分别通过 **14、16、23、6、26、73、37** 项，共 **195** 项。这是改造前基线。后续实施以新增回归、临时签名 feed 端到端演练和一次隔离升级模拟证明新功能，分别记录主机、构建和运行时结果。实施验证记录还应给出自动分配、旧包复用、写账前复核、复建漂移的数量及耗时。生产发布和物理设备部署是独立操作。

## 7. 接手者可直接运行的核查命令

从仓库根目录执行。第一段对固定快照和本地候选验签并打印有序依赖，仅在临时目录提取；按第 3 节的 SHA-256 对齐样本。若本地构建包已被下一次构建替换，可用小型签名 fixture 继续开发，将新的现场读数另行记录。

```bash
bash <<'SH'
set -eu
published=/srv/openwrt-feeds/public/snapshots/20261122T052658.620916Z/base
rebuilt=bin/systemd/packages/x86_64/base
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
mkdir "$scratch/keys"
cp public-key.pem "$scratch/keys/public-key.pem"
apk=staging_dir/host/bin/apk
for package in "$published/librsvg-2.62.4-r5.apk" "$rebuilt/librsvg-2.62.4-r6.apk" \
               "$published/resources-1.10.2-r2.apk" "$rebuilt/resources-1.10.2-r3.apk"
do
    sha256sum "$package"
    "$apk" verify --keys-dir "$scratch/keys" "$package"
    dest="$scratch/$(basename "$package" .apk)"
    mkdir "$dest"
    "$apk" extract --keys-dir "$scratch/keys" --no-chown --destination "$dest" "$package"
done
for elf in "$scratch"/librsvg-*/usr/lib/librsvg-2.so.2.62.4 \
           "$scratch"/resources-*/usr/bin/resources \
           "$scratch"/resources-*/usr/libexec/resources/resources-processes
do
    printf '\n%s\n' "$elf"
    LC_ALL=C readelf --wide --dynamic "$elf" | rg 'NEEDED|SONAME|RPATH|RUNPATH'
done
SH
```

第二段运行现有回归，可在阶段 A 前及每次修改发布决策后复跑：

```bash
bash <<'SH'
set -eu
export PYTHONDONTWRITEBYTECODE=1
for suite in diagnose-apk-rebuild allocate-rebuild-releases elf-abi ucode-abi \
             lan-apk-publisher build-and-publish apk-upgrade-preflight
do
    python3 "scripts/tests/test-${suite}.py"
done
git diff --check
SH
```

接手者提交实现时，请一并交付新版诊断输出示例、真实案例回放结果、临时快照/回执的对应摘要及失败恢复验证记录。发布或部署尚未执行时，验证记录写到实际到达的环节即可。[现有 LAN APK 工作流](lan-apk-feeds.md) · [ELF 迁移与精确依赖](elf-abi-upgrades.md)
