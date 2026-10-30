# Custom 跨维护分支候选审查（2026-10-30）

本次审查上次 custom 更新报告中的 12 项，核对实时上游发布元数据、
候选源码、当前配方、已准备源码、依赖与本地补丁。包版本、注册表策略、
`.config` 和现有构建/部署状态保持不变。下载和试验均位于私有审查目录。

结论：3 项可优先进入升级构建验证；4 项有明确配套工作；5 项保留当前版本。
“可进入验证”不等于已完成目标包构建或桌面验收。

| 包 | 当前 → 审查后的候选 | 结论和依据 |
| --- | --- | --- |
| at-spi2-core | 2.60.7 → 2.62.1 | 优先升级验证。候选为稳定版；libatspi、ATK、atk-bridge 的 SONAME 主版本未变，当前 dbus-daemon、systemd、introspection 配置项仍存在。需要验证辅助功能服务与 GTK 3/4、GNOME 会话。 |
| evolution-data-server | 3.60.2 → 3.62.1 | 配套升级。现有 GI 隔离补丁零 fuzz 应用，但 libcamel CURRENT 67→68、libedataserver CURRENT 27→28，AGE 均为 0，意味着 SONAME 变更；需要检查反向依赖、重建实际 ELF 消费者，并验证 GNOME Shell 的 EDataServer/日历 GIR。不能仅改版本后单包替换。 |
| flatpak | 1.18.4 → 1.19.2 | 保留 1.18.4。1.19.2 的官方 release 设置 prerelease=true，正文声明首次稳定版将是 1.20.0。此候选不应被显示成普通稳定跨分支升级。 |
| gcr3 | 3.41.2 → 报告中的 4.4 | 保留。GCR 4 是另一套 API；本树已独立提供 gcr4 4.4.1，gnome-shell 依赖它，gnome-keyring 仍依赖 gcr3。 |
| intel-media-driver | 26.3.5 → 报告中的 600.0132；另发现 26.4.1 tag | 保留 26.3.5。600.0132 指向 2018-04-20 的提交，属于数字排序误报。完整标签扫描还发现 26.4.1（比 26.3.5 领先 35 个提交），但该 tag 没有对应发布 API 记录（HTTP 404）；最近正式季度 release 仍为 26.3.5（2026Q3），匹配本树 gmmlib 22.10.2 和 libva 2.24.1。不要仅按 tag 数字自动换到下季度代码。 |
| libgtk3 | 3.24.52 → 报告中的 4.24 | 保留。GTK 4 与 GTK 3 API/ABI 不兼容，本树已经独立提供 gtk4 4.24.1；GTK 3 应持续维护 3.24 系列。 |
| libgweather | 4.4.4 → 4.6.0 | 配套升级。GI 补丁零 fuzz 应用，但候选构建无条件查找 gweather-locations，且位置数据库已从本库分离。本树没有对应配方/注册/依赖；需要新增数据包、正确的 locations_db pkg-config 路径和运行时数据，再验证 GNOME 天气/位置读取。 |
| libibus | 1.5.34 → 报告中的 20080901 | 保留 1.5.34。20080901 指向 2008-08-31 的提交，是旧日期标签误报；完整 1.x.y 标签扫描最新仍为 1.5.34。 |
| libportal | 0.9.1 → 0.11.0 | 优先升级验证。官方稳定发布；libportal/GTK 后端的库版本仍是 1.0.0，GIR 仍为 1.0，GTK 3/4 后端配置保留。GIO 最低要求从 2.72 提高到 2.80，本树 GLib 2.90.1 满足；仍需交叉构建、GIR 和文件选择/portal 调用验证。 |
| node-bin | 24.22.2 → 26.13.0 | 配套升级。26.13.0 已于 2026-10-28 进入 Lithium LTS。官方 x64 包 SHA256 校验通过；ELF 新增 libatomic.so.1 依赖，当前配方没有 +libatomic；归档不含 Corepack，但配方仍无条件创建 corepack.js 链接，直接升级会留下断链。还需重建使用旧 Node ABI 的原生扩展；候选 NODE_MODULE_VERSION=147。宿主机运行检查通过，不代表目标机验证。 |
| python-pyparsing | 3.2.5 → 3.3.3 | 优先升级验证。纯 host 构建工具，要求 Python >=3.9。本树当前 Flatpak variant-schema-compiler 的 flatpak-variants.gv、ostree.gv、performance.gv、sample.gv 在候选上全部成功；生成 C 和头文件与 3.2.5 逐字节一致。SPICE 使用单独 pin 到 2.4.7 的 host requirements，不应顺带更改。 |
| spice-gtk | 0.41 → 0.43 | 配套升级。001-wayland-only-gtk.patch 在新 meson.build 上失败；上游已将 X11 改为可选探测，需判断本地补丁是否可删除或按新的 VA-X11/GTK 后端逻辑重写。002-redraw-gl-after-monitor-ready.patch 零 fuzz 应用。后续还需编译、GIR、virt-manager/SPICE 连接和 GL 重连验证。 |

## 验证范围

- Pyparsing sdist 对照 PyPI SHA256 校验，Node x64 归档对照官方 SHASUMS256 校验。
- 候选源码分别展开在私有目录：EDS、libgweather 的现有补丁通过；SPICE
  第一补丁失败，第二补丁通过。没有改变正常 build_dir 中的源码。
- Pyparsing 四个真实消费 schema 均成功，并与原版生成物进行字节比较。
- Node 新 ELF 的 NEEDED 表及归档内容已检查；宿主机执行确认 v26.13.0/Lithium/ABI 147。
- 未执行上述候选的完整目标包构建、固件构建、物理设备安装或桌面验收。

## 更新器需要单独修正的审查提示

1. GitHub 项目的跨分支 `review_version` 当前直接取数字最大 tag，尚未像实际
   更新候选那样校验 draft/prerelease，导致 Flatpak 开发版也进入待审列表。
2. Intel 应按正式季度 release 跟踪，或显式限制其 tag 家族/发布成熟度；
   IBus 应排除历史纯日期标签，避免“最高数值”遮蔽真正维护分支。
3. gcr3、libgtk3 的目录发现应限制在本包 API 主版本；GCR 4、GTK 4 已由独立
   配方维护，不应持续提示为本包升级。
4. EDS、Node、libgweather 和 SPICE 的分支保护有实际价值，应在配套改动和
   验证完成后再推进。不要统一把所有包 policy 改为 stable。

建议下一批先完成 python-pyparsing 3.3.3、at-spi2-core 2.62.1、libportal 0.11.0
的目标/host 包构建验证，再推进 Node 的依赖与 Corepack 配方修正。

## 可复核的一手资料

- [AT-SPI 2.62.1 源码和发布说明](https://download.gnome.org/sources/at-spi2-core/2.62/)
- [EDS 3.62.1 源码和发布说明](https://download.gnome.org/sources/evolution-data-server/3.62/)
- [Flatpak 1.19.2 官方预发布](https://github.com/flatpak/flatpak/releases/tag/1.19.2)
- [Intel 正式发布列表](https://github.com/intel/media-driver/releases)
- [Intel 600.0132 对应旧提交](https://github.com/intel/media-driver/commit/39204285bd5f24862ded8cedfd8aab3c2be96734)
- [Intel 26.4.1 tag](https://github.com/intel/media-driver/tree/intel-media-26.4.1)
- [GTK 3→4 官方迁移说明](https://docs.gtk.org/gtk4/migrating-3to4.html)
- [libgweather 4.6.0 源码](https://download.gnome.org/sources/libgweather/4.6/)
- [IBus 20080901 对应旧提交](https://github.com/ibus/ibus/commit/17eeeb8dd2ba385b1a9e67beb386abc83852a7c1)
- [libportal 0.11.0 官方发布](https://github.com/flatpak/libportal/releases/tag/0.11.0)
- [Node 26.13.0 LTS 发布及 libatomic 说明](https://nodejs.org/en/blog/release/v26.13.0)
- [Pyparsing 3.3.3 元数据](https://pypi.org/pypi/pyparsing/3.3.3/json)
- [SPICE GTK 源码目录](https://www.spice-space.org/download/gtk/)

私有原始证据：`.git/custom-branch-review/20261029T160129Z`。
