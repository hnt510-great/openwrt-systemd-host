# ucode ABI 升级、WireGuard 修复与部署记录

## 根因

2026-10-20 远端在 01:41 执行 `apk upgrade`，01:44 重启。
上一轮启动日志中 `WIREGUARD` 正常上线，重启后未恢复。
接口配置、4 个 peer、`wireguard.uc` 和内核模块均存在，但 netifd 未注册
WireGuard 协议，ubus 显示 `proto=none`、`NO_DEVICE`。

ucode 更新将 ABI 从 `20230711` 改为 `20261009`。远端 netifd 仍链接
`libucode.so.20230711`，全局 ucode 模块目录已经安装新版模块。
使用旧解释器加载当前 WireGuard 文件可复现
`fs.so: undefined symbol: ucv_metamethod_lookup`；匹配的旧解释器和旧模块、
以及匹配的新解释器和新模块都能注册同一份 WireGuard 文件。

普通共享库的版本化名称允许两代 libucode 共存，却不能保证嵌入解释器和
全局 C 模块目录使用同一 ABI。另一个问题是本地重新编译 netifd 后仍是
`2026.09.11~06d06c86-r1`，APK 不会将已安装的同版本包升级。
netifd 还缺少它实际链接的 `+libucode` 直接依赖。
审计同时发现远端 `liblucihttp-ucode` 仍链接旧 ABI；此前 rpcd 的故障属于
同类问题，所以仅修复 WireGuard 包不足以防止复发。

## 修复方案与实现

1. netifd 补充 `+libucode` 并提升到 r2；ucode 提升到 r2、rpcd 到 r3。
   LuCI feed 中 lucihttp、html、lua 和 luci-base 的对应重建也提升版本。
   luci-base 继续跟随 feed 的源版本，以 release 后缀标识原生模块重建。
2. `include/package-pack.mk` 在 APK 打包时调用 `scripts/ucode-abi.py`。
   检查实际 ELF 的 `DT_NEEDED`，拒绝链接到非当前 ABI 的产物；也识别
   `/usr/lib/ucode/` 下没有显式链接 libucode 的 C 模块。
   使用者自动增加 `libucode20261009` 和 `ucode-abi=20261009` 依赖。
   唯一的 `ucode` 解释器包提供 `ucode-abi=20261009`。
   未来 ABI 变更后，求解器会拒绝留下旧 ABI 使用者的部分升级。
   兼容库本身仍可保留，但不代表允许混用嵌入运行时和 C 模块。
3. LAN 发布预检检查每个相关包的最新版本，包括增量发布保留的包。
   解包检查 ELF、ABI 锁和解释器提供值；不匹配或遗漏锁时停止发布。
   相关解释器、库和使用者的同名同版本内容变化也必须提升 release，
   防止重编译后设备仍停留在旧二进制。旧版本 APK 保留用于历史回退，
   校验对象是各包的最新候选版本，而非要求所有历史版本使用新 ABI。

这些保护适用于本树生成和发布的 APK；未迁移的历史包、外部包以及其他
共享库的 ABI 兼容性需要相应的依赖和版本管理，不能据此宣称一并解决。

## 本地验证

按请求未做 VM、QEMU 或整镜像验证。

- netifd、ucode、rpcd、lucihttp、ucode-mod-html、ucode-mod-lua 和 luci-base
  的包级构建通过。
- `python3 scripts/tests/test-ucode-abi.py`：6 项通过；包含真实 ELF 的旧 ABI
  拒绝测试，以及真实 APK 求解器对部分升级拒绝、配套升级接受的测试。
- `python3 scripts/tests/test-lan-apk-publisher.py`：17 项通过；覆盖跨 ABI
  拒绝、增量保留的旧使用者、同版本重建拒绝及发布失败时不切换 feed。
- `python3 scripts/tests/test-build-and-publish.py`：40 项通过。
- `conf --fatalrecursive` 严格检查通过，输出写入临时文件，原 `.config`
  校验和不变；主树及 LuCI feed 的 `git diff --check` 通过。

发布预检曾拦截遗漏 ABI 锁的 luci-base。补齐直接依赖和版本并重建后，
预检通过；这说明预检检查了保留包，而非只检查本次手工选择的修复包。

## 远端部署与验收

2026-10-20 发布快照：`20261020T123255.747399Z`。
23 个配方分包产物发布到 base/luci，kernel channel 保持 unchanged。
从中仅选取远端需要的 17 个包：libucode、ucode、netifd、rpcd-mod-ucode、
liblucihttp-ucode、luci-base 和 11 个 ucode 模块。

备份及安装、模拟、激活日志位于远端：
`/root/wireguard-abi-repair-20261020/`，目录仅 root 可访问。
所有 APK 通过远端已有信任库验签，再通过无网络、空仓库的精确事务模拟，
随后使用完全相同的 17 个文件安装。没有运行全量升级。

通过 `/etc/init.d/network restart` 保留 procd 控制，在后台执行激活。
20:33:44 开始，20:33:51 确认 LAN、PPPoE WAN、WireGuard 和默认路由恢复。
未重启整机。

验收结果：

- `WIREGUARD` 为 `up=true`、`proto=wireguard`，地址 `10.0.0.1/24`，
  UDP 20010 的 IPv4/IPv6 socket 均存在，4 个 peer 已加载。
- netifd 进程使用 `libucode.so.20261009`；无进程映射旧 libucode，
  已安装的 ucode C 模块不再引用旧 libucode SONAME。
- fs、ubus、uloop、uci、rtnl、nl80211、digest、log、math、html、lua、
  lucihttp、luci.core 共 13 个模块导入成功；`luci.getFeatures` 成功。
- DNS 经本机解析成功。未登录的 LuCI 请求正确返回带登录页的 403；
  临时授权会话访问状态页返回 200，会话已销毁。
- 原有所有 `/etc/config/*` 文件校验通过，network、firewall、dhcp、
  passwall、luci、rpcd、uhttpd 均保持原样。boot ID、内核 release 以及
  kernel/kmod/image 包集合不变；没有安装内核或模块。
- 刷新远端索引后，目标包可正常参与求解；另有同配方的 rpcd 核心和
  liblucihttp0 新 release 可升级，本次未扩大安装范围。

验收时尚无客户端重新握手，握手和流量计数为零。因此已证明接口、密钥
配置装载及服务恢复，未证明本次恢复后的客户端到端隧道通信。
