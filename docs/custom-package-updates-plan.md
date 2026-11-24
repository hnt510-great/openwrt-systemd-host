# Custom 包自动更新与桌面依赖兼容修复计划

**状态**　已实施（2026-11-24）。已完成来源登记修复、离线校验、`--check` 容错汇总、GNOME 整数系列与 `mozjs140` 父目录发现、Qt6 12 模块原子联动组、桌面联编依赖与 `xdg-desktop-portal` 附带源码联动、`local` 条目分类，并通过全部离线单测（58 项）、全量只读检查（0 失败）以及隔离工作树真实候选构建验收（`gnome-control-center` 51.2.1、`nautilus` 51.2、`mozjs140` 140.17.0 与 `gjs` 联编）。

维护版本继续通过 `./scripts/feeds update -a` 发现，下载、应用补丁和编译沿用 OpenWrt 原生 `make` 流程。Qt、Plasma 或 GNOME 出现新发行系列时，更新器应报告候选版本和受影响的包，待相关组件一起验证后采用。[现有更新指南](custom-package-updates.md)

## 审查基线

当日按组只读检查覆盖全部 300 个顶层 custom 配方，得到 250 个 `current`、39 个 `local`、7 个 `review`、2 个 `available` 和 2 个 `failed`。`current` 只反映登记规则能看到的版本。例如，`mozjs140` 的查询地址固定到了单个发行版，即使上游发布了新的 140 ESR 源码也会显示当前版本。

## 实施步骤

### 1. 修复来源登记和全量检查

- 在注册表中将 `qcoro6` 和 `qtkeychain-qt6` 改用已支持的 `provider: github`、`catalog: releases` 和 `project`，分别保留带 `v` 和不带 `v` 的标签匹配规则。[注册表](../configs/custom-package-updates.json)
- 更新器先离线检查配方覆盖、来源类型、必填字段、`follow` 路径和循环依赖。登记错误应在下载源码或写配方前一次报告。
- 在 `--check` 中，一个上游查询失败后继续检查其余独立组，最后汇总失败项并返回错误状态。更新模式继续保护已跟踪配方的本地修改，联动组内任一成员失败就停止写入该组。[更新器实现](../scripts/update-custom-packages.py)

### 2. 修正 GNOME 和 mozjs 的维护分支

- 逐项核对使用整数发行目录且配置为 `series` 的 20 个 GNOME 条目。对使用 `51/` 这类目录发布维护版本的项目，允许 `51.1 → 51.2` 和 `51.2 → 51.2.1`，排除 alpha、beta 和 rc。扫描父目录时识别下一整数系列，单列供审阅。GTK、GLib、GJS 按各自的上游分支规则处理。
- 将 `mozjs140` 的发现入口移到 Mozilla 发行父目录，仅匹配 `140.*esr` 的正式源码，并从候选版本目录获取校验值。保留配方的版本格式和 `mozjs-140` ABI，安排 GJS 联编。
- 用控制中心 `51.1 → 51.2.1`、Nautilus `51.1 → 51.2` 和 mozjs 上游 `140.15.0esr → 140.17.0esr` 覆盖原先的三个漏报。

### 3. 将 Qt 的 12 个模块作为一个更新组

- 以 `feeds/video/frameworks/qt6/common.mk` 为版本基准，登记 video feed 的 6 个 Qt 模块和主树的 6 个 custom 模块。选择任一成员都展开整组。默认查询 `6.11.x`，将 `6.12.x` 等新系列列为迁移候选。
- 为同一个版本收齐 12 份源码及哈希，准备公共版本、各模块配方和 video 补丁镜像的完整变更，然后检查两个仓库的基线和相关文件。缺少归档、哈希不符或遇到本地修改时，报告具体模块并保留原组合。
- 复用现有更新器的备份和失败恢复机制，覆盖主树、video feed 和补丁镜像。写入中途失败时恢复本批次已写文件；两个仓库分别保留自己的提交历史。[video feed 镜像清单](../configs/kde-plasma-feeds.json)

### 4. 验证桌面组件之间的依赖

| 触发变更 | 联动处理 |
| --- | --- |
| Qt 或 KF6 更新 | 保留 ECM/KF6 的 55 项联动组。把受影响的 host 工具、目标库、QML 插件和反向依赖纳入构建，尤其是使用 Qt 私有 API 的 KWin，以及 Plasma Workspace、Dolphin 等消费者。 |
| Plasma 或 KDE Gear 更新 | 保留 Plasma 的 32 项组和 Konsole/Dolphin 的 2 项组。扩大目录发现范围，Plasma 自动跟踪当前维护线，Gear 换发行系列时单列审阅。让候选源码的 CMake 配置检查实际最低版本。例如当前 KWin 和 Plasma Workspace 均要求 Qt 至少 6.11.0、KF6 至少 6.30.0。 |
| GNOME 核心组件更新 | Mutter API 变化时联编 Shell，mozjs 变化时联编 GJS，Shell 跨主版本时检查 Kimpanel 的兼容声明。通过候选源码的 Meson 配置检查依赖版本；控制中心、Nautilus 等独立应用按各自维护版本更新。 |

报告中列出触发升级的包、需要联编的包及阻塞原因。构建范围包含当前配置选为 `=m` 的 Plasma 组件。[Plasma 组件布局](kde-plasma.md) · [GNOME 桌面集成](gnome-desktop.md)

### 5. 处理本地维护包和附带源码

- 逐项核对 39 个 `local` 条目，注明本地维护、随内核或 libc 派生、固定上游源码三种情况。本地整合包沿用 `PKG_RELEASE`，派生包沿用对应基础组件的版本机制。
- 对固定源码写明升级条件。Sunshine 的正式发行与 `sources.json` 中的 gitlink 归档和哈希一起更新；virtiofsd 同步处理源码和 Cargo vendor 哈希；Kimpanel 检查 Shell 兼容性；daed 保留组合源码，直到上游发行满足配方登记的条件。
- 复查 iso-codes、hunspell-en、libutempter 等数据或提交固定项，以及 `xdg-desktop-portal` 额外下载的 Flatpak 接口源码。对能够可靠发现和校验的输入登记联动关系；其余条目列明固定理由和重新评估条件。

### 6. 接回日常更新和构建

- `--check` 展示当前版本、候选版本、所属组、待审阅或失败原因。`feeds update` 准备已核验的配方，`feeds update -i` 延续只生成索引的行为。
- 跨系列候选先在隔离工作树准备，通过原生 `make` 执行相关包的补丁、配置和构建检查，再采用通过验证的组合。使用当前 `.config` 的副本，保留主工作区配置和独立 feed 历史。
- 将更新器修复与首批软件升级分别提交。后续需要发布时，沿用仓库的 APK 版本唯一性、保留包依赖、ELF/SONAME 和路由器升级模拟检查。[发布就绪规则](publication-readiness.md)

## 验收

1. **一次离线测试。** 运行 `python3 scripts/tests/test-custom-package-updates.py`。在现有套件中覆盖错误来源、GNOME 和 ESR 版本选择、跨系列进入审阅，以及模拟 Qt 最后一个模块缺失时整组配方和镜像仍保持原样。
2. **一次全量只读检查。** 运行 `python3 scripts/update-custom-packages.py --check`。全部已登记配方都有结论，两项 GitHub 来源错误消失，三个已知漏报在升级前可见，主树和 video feed 的改动与运行前一致。返回码 0 表示检查通过且没有候选，1 表示有更新或待审阅项，2 表示检查出错。
3. **一次真实候选构建。** 在隔离工作树中下载、准备并定向编译控制中心、Nautilus、mozjs140 和 GJS。审查时已核对两个 GNOME 候选的官方 SHA-256，控制中心的 3 个补丁及 Nautilus 的 1 个补丁均以零 fuzz 应用。此次以包构建和 GJS 联编结果验收。Qt 当前维护线用离线用例验证联动；实际采用 Qt 6.12 或桌面新系列时，再运行对应桌面的一次 VM 冒烟检查。
