# daed 原生客户端功能移植计划与实施交接

交接日期为 2026-11-24。本文是待实施的规格和验收清单。本轮完成了源码调查，功能开发、真实节点基线及 V01–V11 验收均待执行。接手者从“阶段 0”开始，实施前由管理员提供测试用 VLESS 节点地址。现有功能说明见 [daed 指南](daed.md)，既往测试记录见 [daed 验证记录](daed-validation.md)。

## 1. 已定范围与交付物

- **原生能力优先。** 在 daed 的 React 面板和 dae-wing Go 后端实现设备 ACL、规则列表和更新、全局 DNS 分流、增强订阅、代理链、有序主备及诊断。维持当前 dae、outbound、eBPF 以及现有五个包补丁。LuCI 继续负责服务开关、状态、日志和面板入口。
- **配置由管理员在 daed 内创建。** 不开发 PassWall UCI/备份导入、迁移向导或仅管理模式。用户仍可从分享链接添加节点、从订阅获取节点、粘贴规则文本。沿用现有 PassWall/daed 服务互斥。
- **默认手动应用，可按运行配置开启自动应用。** 定时下载、保存草稿和完整应用是独立操作。组内主备切换使用 dae 的运行时选点接口。
- **以 KVM 为最终验收。** 包含从 LAN 客户端经过真实 VLESS 的 TCP 透明代理和负对照；节点支持 UDP 时另验真实 UDP。可控的双栈、UDP、两跳和故障场景均在隔离 VM 验收。本任务范围止于源码、嵌入面板、APK、测试镜像及 VM 验证记录。发布 feed 和切换物理路由器另行授权。
- 本期范围以外的功能有显式 SOCKS/HTTP 多端口入站、托管外部 Xray/sing-box、XHTTP、mKCP、WireGuard 节点、FakeDNS、每设备独立 DNS、按入接口或动态 nftset/BitTorrent 分类，以及 HAProxy 精确加权调度。表单或导入器遇到不支持的关键选项，要指出具体选项。

## 2. 接手时先定位版本和代码

在主仓库根目录工作。开始前阅读 [AGENTS.md](../AGENTS.md) 和 [CLAUDE.md](../CLAUDE.md)，复核下表中的版本。主树、daed 子模块和 PassWall feed 分别有自己的 Git 历史。

| 2026-11-24 核对对象 | 本次依据 | 开发时的用途 |
|---|---|---|
| 主树 `ac1d54acbcf0` | [daed Makefile](../package/custom/daed/Makefile)，包 `2.1.3-r1` | 配方固定 dae 核心 2.1.3 和 `olicesx/outbound@v0.0.0-sticky-ip.0.20260918090140-cc86ced2e683`。核心版本优先查配方；总览文档中仍有旧版描述。 |
| daed 子模块 `139e0d2ca68a` | [维护说明](../package/custom/daed/src/MAINTENANCE.md) | 根目录为本地维护的 dae-wing，源自 `b089b56`；`web-src/` 为 daed v2.1.1 面板工作区，`webrender/web/` 为实际嵌入包的产物。后端、前端源码及重建的资源均在该子模块维护。 |
| 实际参与编译的 Go 源码 | `build_dir/target-x86_64_glibc/daed-2.1.3/{dae-core,third_party/outbound}` | 适合核对函数、测试包和固定版本行为。干净 checkout 需先由配方 prepare 或 compile 组装来源。历史 `daed-2.1.1` 目录可能同时存在。持久修改放回子模块、主树测试或配方。 |
| PassWall 客户端 feed `21a1b9fc` | [客户端设置目录](../feeds/passwall_luci/luci-app-passwall/luasrc/model/cbi/passwall/client)，本树构建使用 Xray 26.11.9、sing-box 1.14.4 | `acl_config.lua`、`shunt_rules.lua`、`node_subscribe_config.lua`、`socks_config.lua` 定义参考交互；`root/usr/share/passwall/{nftables.sh,rule_update.lua,subscribe.lua,clash_subconverter.lua}` 可核对实际语义。使用仓库自带默认配置、规则和合成测试数据。 |

以下目录简写均相对 daed 子模块，`core/` 和 `outbound/` 分别指上表编译目录的 `dae-core/` 和 `third_party/outbound/`。

| 要找的能力 | 可复用入口与容易遗漏的事实 |
|---|---|
| 配置组装与恢复 | `graphql/service/config/mutation_utils.go` 的 `Run` 读取已选 Global/DNS/Routing，推导必要组、展开节点、交给 `dae.ChReloadConfigs`，随后登记运行状态。`cmd/run.go` 的 `restoreRunningState` 仍按当前已选资源重装。`run(dry:true)` 加载空配置并设为停止。`dae/run.go` 完整重载会拆除旧控制面，可能中断已有连接。 |
| 运行状态与并发 | `db/system.go` 记录运行对象、版本、组 ID 和版本和；`graphql/service/general/dae_resolver.go` 用它们计算 modified。`Run` 已有互斥锁，但组装中的 map 遍历及同名节点编号影响结果顺序。新增内容摘要及主备索引不能依赖 map 顺序。 |
| Dashboard 和接口 | `graphql/root_schema.go`、`graphql/schema_chains.go`、`graphql/service/` 为管理员 GraphQL 入口。前端位于 `web-src/apps/web/src/`，页面在 `pages/Orchestrate/`，请求在 `apis/`。`RoutingFormModal.tsx` 已有 GFW、非中国大陆、仅中国大陆、全局、MAC 模板；`components/DNSFormModal/` 已能编辑上下游、请求及响应规则。 |
| 节点和订阅 | `db/node_utils.go:NewNodeModel` 会构造实际 dialer。`graphql/service/subscription/mutation_utils.go` 已有 Cron、SIP008/Base64、16 MiB 响应限制、默认先直连再经 dae 路由重试。`UpdateById` 当前会删掉部分节点行后重新导入。`db/group.go` 已支持订阅按名称正则入组。`dae/run.go` 要求订阅在 wing 侧展开成 `conf.Node`。 |
| 指定组下载 | `dae/httpclient.go` 使用 `OutboundControlPlaneRouting`；它可能按规则直连。强制指定组须取当前控制面的组映射，用明确出站调用 `core/control/tcp.go:RouteDialTcpContext`。DNS 解析路径与 HTTP 连接出口分别描述。 |
| 策略校验、容量 | 参考 `core/cmd/validate.go` 的优化、DAT 展开及 `control.RegisterRoutingProgramParsers`，以及 `core/component/dns/` 的验证。`core/control/routing_matcher_builder.go` 里的端口范围逐项产生 match set，同类域名可共享一个 set。包上限为 1024；内核构造器的精确计数和部分结构为私有。`core/control/control_plane.go` 还会按配置插入 sniff-punt 条件。 |
| 代理链、Naïve | `outbound/dialer/register.go:NewNetproxyDialerFromLink` 按 `->` 分段、从右向左包装；用真实转发的端点校验网络经过顺序。`outbound/dialer/naive/naive.go` 为 `naive+https` 提供 HTTP/2 TCP 出站，创建 `naive+quic` 节点时会报错。不能只依据注册的 scheme 判断支持。 |
| 主备与探测 | `core/control/control.go:OutboundGroups`、`core/component/outbound/dialer_group.go:SetSelection/SetSelectionBoth` 是运行时入口。`core/cmd/nativeapi_groups.go` 提供成员解析和策略判断参考。现有 wing 的 GraphQL Policy 只有 fixed/random/三种延迟策略，`Run` 对 fixed 组限制单节点。`graphql/service/node/latency_probe.go` 已有经节点的 TCP HTTP 探测，`core/component/outbound/dialer/connectivity_check.go` 提供 `HttpCheck` 和 `DnsCheck`。 |
| 运行规则追踪 | `core/control/routing_trace.go:RoutingTraceInput` 无源 MAC，遇到 MAC 条件可能返回 `src_mac` 缺失。`dae/run.go:newControlPlane` 当前未设置 `ControlPlaneBuildOptions.RoutingTraceEnabled`。由 wing 在需要追踪的运行配置启用该选项；查询前检查 `RoutingTraceAvailable()`。核心有 trace 步数上限，追踪不可用时显示原因。 |
| VM 和凭据 | [daed KVM 脚本](../scripts/tests/test-daed-vm.py) 当前使用 `restrict=on,ipv6=off` 和模拟 SOCKS5 CONNECT。其 `gql` 将变量放入 curl 命令；[通用 Guest 驱动](../scripts/test-image-network.py) 同时保存 serial 日志和命令日志。`dae/run.go:newControlPlane` 在 debug 级别还会序列化完整配置。真实 VLESS 测试要覆盖这三条泄露路径。 |

## 3. 配置底座与兼容设计

继续使用 `wing.db`。在现有 Global、DNS、Routing、Node、Group、Subscription 模型上增量建表或加字段。升级前创建一致性 SQLite 备份，含 WAL 的库使用 SQLite 的一致性备份方法。所有旧用户、认证、手写规则、配置选择和已有调用方保留原有用法。

| 对象 | 数据与约束 |
|---|---|
| 可视化策略和 ACL | 隶属现有 Routing，保存编辑模式、修订号、默认动作、有序 ACL 和列表引用。手写 routing/DNS 保留原文。可视化策略允许查看生成文本、另存为手写副本。旧文本更新接口编辑旧记录仍然有效，对受管理的生成文本返回可操作的冲突提示。 |
| 列表与内容版本 | 保存稳定列表 ID、类型、静态条目或远端来源、更新计划、最后成功内容及摘要。运行快照固定内容版本；删除仍被引用的列表时显示引用者。 |
| 节点与链 | 沿用节点 ID；保存链的有序叶子成员 ID，链可进入现有组。删除或刷新时核对组、链和主备引用。 |
| 主备配置 | 按组保存主节点、备用顺序、探测目标、阈值和回切策略；按当前控制面和协议维护实时选择、计数及最近切换原因。 |
| 成功快照 | 保存恢复所需 Global、DNS、Routing、节点链接、组成员、链展开结果、依赖及内容版本。至少保留当前和上一成功版本。快照随数据库权限保护；生成文本差异、诊断与报告需脱敏。 |

从 `config.Run` 提取候选装配。确定必要组时计入策略、链、主备和强制下载组的依赖。保留既有节点别名行为，并显式排序、处理同名冲突。相同输入的有效文本、成员映射及摘要必须可复现。

1. **保存草稿**允许暂缺引用，返回修订和可定位诊断。保存不得调用 reload。
2. **预览**用一次一致性读取装配整个候选，返回规则次序、所用列表版本、成员、差异、来源 ID 和候选摘要。做无副作用的语法、引用、节点、DNS、Geo 及容量预检。用归一化后的条件计数，覆盖端口及自动插入规则；用核心实际加载的边界用例校准。静态校验无法证明内核资源分配成功。禁止用 `run(dry:true)` 预览。
3. **应用**携带草稿修订和候选摘要，串行复核依赖，再加载候选。控制面 ready 后提交成功快照及 System 状态。候选失败走既有回退；候选已运行但数据库提交失败时恢复上一成功快照。若恢复也失败，显示代理实际停止/失败状态并保留成功快照。
4. **重启与回退**以最后完整提交的快照恢复，回退直接使用当时的节点和列表版本。尊重管理员已停止代理的状态。旧库首次启动沿用原恢复入口，首次成功应用后切换到快照恢复。
5. **定时更新**网络获取在事务外，提交时校验来源修订，手动和定时请求按来源串行。运行配置可选择自动应用。合并同轮依赖变化，无有效差异则不重载。若管理员有尚未应用的编辑，只显示待应用差异。页面清楚标明完整应用有连接中断窗口。

## 4. 功能实施与前端交互

### 4.1 设备 ACL、规则源与 DNS

- 「路由 → 设备策略」展示启用、顺序、来源、目的、协议/端口、动作及出口，支持增删、排序、复制和继承全局。通过 DHCP 租约及邻居表提供设备提示，手工录入适用于离线设备。设备名仅作显示；保存时明确选用 MAC、固定地址或网段。可参考 [本树设备信息采集](../package/custom/router-audit/files/router-audit)，避免依赖 router-audit 服务运行。
- 同一来源列表内是“任一”，来源与目的、协议、端口之间是“同时满足”。混合 MAC 和 IP 的来源需要展开为等价分支，保持规则次序。地址范围精确分解为 CIDR，支持 IPv4/IPv6。动作包括组、直连、阻断及继承。路由器自有流量与 LAN 转发分别受 WAN/LAN 绑定约束。
- 独立处理“不代理端口”“允许代理端口”“仅阻断本应代理的端口”。参考 PassWall `nftables.sh` 中 ACL 跳过端口、列表例外和 TCP/UDP drop 条件的生成顺序。验收必须同时验证代理客户端的 UDP/443 被阻断、直连客户端访问同一 UDP/443 成功。
- 「规则列表」管理直连、代理、阻断、自定义组、GFW、国内域名和 IPv4/IPv6 网段。支持粘贴文本、静态维护、远端源与 Cron。解析纯文本域名/CIDR、常见 GFWList 和 dnsmasq 域名条目；保留完整、后缀、关键字、正则、例外和次序。无法表达的例外须报告行号并阻止自动应用。显示增删数量、引用者和最近成功版本。更新格式错、空响应、HTML 错页或超限时保留好版本。既有 GeoIP/GeoSite 由系统数据包提供。
- 「DNS」复用上下游及请求/响应编辑器，支持导入已维护域名列表作匹配条件、按查询类型选上游、按返回地址重查及本地域名走 dnsmasq。区别 `direct` 的 DNS 接管行为与 `must_direct` 的绕过行为。域名规则依赖 dae 观察到的 DNS 或成功嗅探；域名位图按目的 IP 共享，设备使用加密 DNS 或目标不可嗅探时，展示并验收实际 fallback。参考 `core/docs/en/configuration/{routing,dns}.md`。

### 4.2 订阅、协议表单与链式节点

1. 在现有订阅页加入格式识别、每订阅 UA、自动/直连/指定组下载、关键词保留/排除及冲突优先级、流量/到期日、计划与刷新差异。保留已有 Cron 和分组正则。导入过滤决定入库，分组正则决定入组。
2. 后端按“下载、识别、节点转换、关键参数校验、过滤、与旧版本比较、事务提交”执行。保留 SIP008、现有节点链接/Base64，增加 Clash YAML 的 `proxies`。解析 `Subscription-Userinfo`。按实际 outbound 构造 dialer 并检查容易被忽略的参数；错误报告包含协议、参数名、原因或行号，隐藏完整链接。指定组不存在/未运行时明确失败，允许先添加独立节点引导首次下载。
3. 同订阅内相同连接规范化后保留节点 ID，改名原位更新。凭据改变时仅在协议、地址、端口、传输及身份线索能唯一对应时原位更新；歧义、消失或有关键配置无法转换的被引用节点，标为待重绑。不要复用同名陌生节点。运行组、链、主备依赖失效时阻止该候选应用。全空或全无效的响应不替换上次节点集。测试包含旧分组的显式成员和按订阅正则动态加入的成员。
4. 「节点 → 代理链」从左到右显示路由器、前置、落地、目标。链只选叶子成员；保存 ID、顺序和可用性。后端生成 outbound 链并按当前运行配置验证，避免提前承诺组合的 UDP 能力。分别展示“可解析”“单节点探测结果”“整链实测”；定位不到某一跳时保留整链错误。通过真正能转发的两个出口验证顺序。
5. 扩展 `ConfigureNodeFormModal/protocols/registry.ts` 增加 `naive+https`；`naive+quic` 提示本版本缺少该传输。常规 SS/SSR、VLESS/VMess、Trojan、Hysteria2、TUIC、AnyTLS、Juicity、SOCKS5、HTTP(S) 和基础链式出站已有核心实现。只新增确实缺少的表单及管理行为。

### 4.3 分组主备、探测与运行规则诊断

- 在「分组」加入有序主备。由 wing 扩展 GraphQL/模型并将多成员组装配为 dae 原生 `select` 组。保留原固定/随机/延迟组行为。每次建代后以 `OutboundGroups()` 中实际组和成员生成 ID 到运行时索引的映射。运行时变更与重载串行，按组修订和运行代拒绝迟到的探测结果。
- 默认 30 秒一次、5 秒超时、连续失败 3 次切换，主节点连续成功 2 次后按回切开关决定是否恢复。首次优先主节点，备选按用户顺序。某协议达到阈值时切到该协议已探测健康的首个备用；全部失败保留最后选择并展示“无健康备用”。TCP 和 UDP 分别保存状态，只有两者都需切到同一成员时才使用 `SetSelectionBoth`。
- 诊断提供到节点服务器的 ICMP、TCP 建连，以及经候选节点的 URL 和 UDP DNS。测试 URL 可用受控 `generate_204`，以明确状态码判断。UDP 使用节点实际 DNS 往返。显示目标、协议、时间、结果与失败阶段。核心的选择影响新连接；切换本身不关闭无关长连接，已在故障节点上的旧连接可能失效。
- 运行规则诊断必须接到启用了 trace 的活动控制面，携带运行版本。结果区分命中、未命中、输入缺失以及追踪不可用。受控 IP 条件可由 `TraceRouting` 查询；MAC 条件用真实 LAN 身份验收。草稿预览展示将生成的规则，界面上与对活动配置的查询分开。

### 4.4 管理 API 与页面状态

沿用管理员权限、`graphql-go`、现有 React Query 请求与中英文资源。以下为新增接口约定，旧 CRUD 和运行接口继续兼容。

| 操作 | 输入 | 响应及失败处理 |
|---|---|---|
| `savePolicyDraft` | 策略 ID、原修订、结构化 ACL 及默认策略 | 新修订和字段诊断；原修订已变则返回冲突，保留待编辑内容。 |
| `previewPolicy` | 草稿修订、Global 和 DNS 选择 | 候选摘要、依赖版本、已展开规则、错误位置、有效差异、应用影响。 |
| `applyPolicyRevision`、`rollbackPolicy` | 候选摘要与修订，或成功快照 ID | 实际运行版本与结果。失败时返回回退是否成功，禁止将失败候选显示为运行中。 |
| 规则源、订阅、链及主备配置 | 类型化输入、对象 ID 和修订 | 列表版本/刷新差异、受影响引用、链成员与顺序、每协议主备状态。 |
| `testNodePath`、`traceActiveRoute` | 节点或链、探测类型、测试目标，或运行规则查询条件 | 耗时、阶段、运行版本、判定依据及缺失条件。 |

页面标明草稿、待应用、运行中、应用失败四种状态，提供从错误跳回对象的入口。使用 `daed export schema` 输出的 SDL 通过 `SCHEMA_PATH` 驱动前端 codegen。浏览器验收直接访问 VM 内最终 APK 服务的页面。

## 5. 阶段 0 与 VM 拓扑

1. 记录主树、子模块、配方、核心和 outbound 版本；确认用于旧版基线和升级测试的包或镜像实际包含预期版本。历史 [验证记录](daed-validation.md) 中 `2.1.3-r1` 这一节只覆盖主机编译和单测，早期 VM 结果不能计为本需求已通过。
2. 用户在实施前提供真实 VLESS 地址。先检查 `type`、TLS/REALITY、SNI、flow 等与当前 outbound 的兼容性，在旧版 VM 验证节点可达与 LAN 透明访问。记录脱敏结果。如果要求 XHTTP 等当前不支持的传输，向用户指出具体选项并取得兼容节点后再做真实基线。外部连通失败单列证据，V10 保留为待验。
3. 保留现有 `test-daed-vm.py` 快速回归。扩展隔离环境为路由器 VM、提供两个独立 MAC/IP 身份的 LAN 客户端 VM、提供双栈 DNS/HTTPS/UDP 回显和两个代理的 WAN 测试 VM。两代理要能真实转发、记录下一跳和一次性请求标识，可独立切断 TCP/UDP。LAN 流量从被测路由器进出；浏览器经测试 LAN 操作嵌入面板。
4. 对**同一最终镜像**另启临时路由器与 LAN 客户端，测试 WAN 能访问真实节点。测试入口计划新增 `--vless-file`（当前脚本尚无此参数）。用受限临时文件及只读 virtio 块设备传入，客体在内存构造 GraphQL 请求。宿主命令行、串口回显、GraphQL 错误、运行配置 debug 日志、截图及 `validation.json` 只允许脱敏内容。沿用调试脚本中“tail daed 日志到收据”的路径前要先过滤。真实场景结束后清理临时介质和含 `wing.db` 的 VM 写层。保留非敏感测试证据。

### 验收矩阵

| ID | 场景 | 可观察的通过条件 |
|---|---|---|
| V01 | 用旧版 VM 创建账号、订阅、固定组、手写 routing/DNS 并选择运行；升级后重启 | 原账号、内容和引用可用，客户端仍从预期出口访问。首次成功快照后再保存未应用草稿，重启仍恢复已应用版本。 |
| V02 | 两个 MAC/IP 对同一目标应用设备例外和重叠网段规则；调整顺序和启停 | 两个身份看到预期直连/代理标识；顺序变化正确改变实际出口；禁用例外后回到默认策略。 |
| V03 | 按 TCP/UDP、端口和 IPv4/IPv6 分流；测试本地域名、远程上游、响应重查及只有目的 IP 的连接 | 实际出口和 DNS 回应符合各自策略；代理 UDP/443 被阻断且直连对照成功；管理访问和本地域名可用。 |
| V04 | 真实规模的域名/CIDR、重复项、错误例外、容量边界和超限 | 验证有效条目、顺序、引用及编译后容量；坏版本标注错误位置，旧规则继续服务。 |
| V05 | 模拟 YAML、SIP008、Base64、UA、用量头、指定组下载；模拟改名、凭据轮换、重名、HTML、空结果和并发刷新 | 下载服务确认 UA 和实际出口；节点稳定 ID、保留/排除、显式和动态组成员、失效引用均符合设计；坏响应和旧请求不覆盖好版本。 |
| V06 | 维持健康长连接并保存、预览、刷新；测试自动应用、人工草稿、过期摘要、候选加载失败及提交前中断 | 无变化不重载，草稿不会随自动更新发布；有效变更只应用一次；失败或重启后客户端走上一成功出口，并显示真实运行状态。 |
| V07 | 拓扑限制为前置可达落地、落地可达目标；发送一次性标识，随后倒序或关停任意一跳 | 前置记录连接到落地，落地记录连接到目标，HTTP 目标收到标识。顺序错误或缺一跳时访问失败。 |
| V08 | 主节点分别丢 TCP、丢 UDP、完全失效、恢复；测试全部候选失败、回切开关、过期探测 | 阈值和每协议选择正确；新连接经健康备用，切换时 daed PID 和配置版本不变；无关组长连接存活。 |
| V09 | 浏览器用实装面板完成创建、排序、预览、应用、刷新、组链、诊断和重绑 | 页面刷新后配置仍在；草稿与运行状态可区分；中文错误指到具体对象；运行 MAC 查询清楚显示缺失输入。 |
| **V10** | 用户的真实 VLESS，LAN 端清除显式代理，发起新 HTTPS 连接；仅在测试 WAN 阻断节点当次可用地址/端口，解除后复测 | 成功响应同时有 VLESS 组流量增量或拨号证据；阻断后强制代理新连接失败，独立直连对照成功；解除后新代理请求恢复。避免沿用缓存连接或备用出口。TCP 必验，节点支持 UDP 时另测真实 UDP。 |
| V11 | 在最终镜像重跑原有 daed 与 LuCI 回归 | PassWall 互斥、LuCI 限权、默认状态、启停、hook 清理、重启自启和客户端路由均通过。 |

## 6. 开发顺序、构建和交付记录

| 阶段 | 完成后再进入下一阶段的检查 |
|---|---|
| 0．基线和夹具 | 已核对节点兼容性及旧 VM 结果；隔离 WAN 测试出口可区分；日志泄露路径已处理。 |
| 1．配置底座 | 旧库兼容、候选摘要稳定、预览无运行副作用、装载/提交失败可恢复。先建立运行版本和代际标识。 |
| 2．ACL、列表和 DNS | 面板可走完设备选择到应用；V02–V04 从真实 LAN 身份观测数据流。 |
| 3．订阅和稳定引用 | V05 通过；先解决刷新导致的节点 ID 变化，再让链和主备引用节点。 |
| 4．链、主备和诊断 | V07–V09 通过；组内换点无全量重载，无法追踪时有准确说明。 |
| 5．最终打包及验收 | 更新 Go/前端测试、嵌入资源、子模块指针及 `PKG_RELEASE`；同一最终镜像完成所有适用 V01–V11，单列 V10 TCP 和 UDP 结果。 |

前端工作目录为 `package/custom/daed/src/web-src`。使用锁定的 pnpm 10.24.0。`MAINTENANCE.md` 中的旧过滤名 `@daed-revived/web` 与当前 [应用包名](../package/custom/daed/src/web-src/apps/web/package.json) 不符，实际包名为 `daed`。

```sh
pnpm install --frozen-lockfile
# DAED_SCHEMA_FILE 是此次后端用 daed export schema 导出的 SDL 的绝对路径
SCHEMA_PATH="${DAED_SCHEMA_FILE:?set the exported schema path}" pnpm run codegen
pnpm --filter daed check-types
pnpm --filter daed test
pnpm --filter daed build
```

核对 build 实际生成 `apps/web/dist/`，把整套产物同步至子模块的 `webrender/web/` 并清理仅属于旧版的散列资源。OpenWrt 的 Prepare 会排除 `web-src/`，只改 TSX 不会更新包内页面。Go 侧应在含 `dae-core/` 及已补丁 `third_party/outbound/` 的**当前组装树**运行测试；裸子模块 `go.mod` 把 dae replace 到 `./dae-core`。先确保组装树确实包含刚改的源码，再跑配置装配、订阅、分组、节点、路由和 DNS 的单测，对调度、刷新、应用和热切换并发路径增加 `-race` 测试。

主树按 [本地构建说明](local-build.md) 保留已有 `.config`。下面是已有入口；新 VM 用例和真实节点文件参数由实施阶段增加。

```sh
make package/custom/daed/compile -j12 V=s
node scripts/tests/test-luci-daed-view.js
python3 scripts/build-and-publish.py build-only -j12 V=s
python3 scripts/tests/test-daed-vm.py \
    --image "${DAED_VM_IMAGE:?set the final image path}" \
    --work-dir "${DAED_VM_WORK:?set a new work directory}"
```

交付前对主树和 daed 子模块分别执行 `git diff --check`。在 [daed 验证记录](daed-validation.md) 追加本功能专节，记录主树与子模块版本、包 release/APK SHA-256、镜像 SHA-256、Go/前端检查、最终 VM 结果、脱敏收据位置和未覆盖项。状态使用“通过 / 失败 / 待验 / 不适用并说明原因”。V10 TCP 或其他必验项缺失时保留待验状态。本文的调查与设计不作为运行验收证据。
