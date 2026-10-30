# Custom 分支升级及依赖验证（2026-10-30）

已执行前一份候选审查中可推进的七项升级，补齐依赖并完成本地构建。
本次范围是配方、源码补丁、构建和使用目标库的本地冒烟测试。
未发布 feeds、未安装到设备、未重启会话或设备，也未提交或推送 Git。

| 包 | 原版本 | 新版本 |
| --- | --- | --- |
| at-spi2-core | 2.60.7-r5 | 2.62.1-r1 |
| libportal | 0.9.1-r2（有效 APK） | 0.11.0-r1 |
| python-pyparsing（host） | 3.2.5 | 3.3.3 |
| evolution-data-server | 3.60.2-r1 | 3.62.1-r1 |
| libgweather | 4.4.4-r2 | 4.6.0-r1 |
| node-bin | 24.22.2-r1 | 26.13.0-r1 |
| spice-gtk | 0.41-r6（有效 APK） | 0.43-r1 |
| gweather-locations | 新增 | 2026.2-r1 |
| spice-protocol（构建头文件） | 0.14.4 | 0.14.5 |
| gnome-shell（ABI 消费者重建） | 51.1-r2 | 51.1-r3 |

## 依赖和兼容处理

- 新建 `package/custom/gweather-locations` 并登记 custom 更新器，沿
  2026 年度分支更新数据版本。使用 host PyGObject 生成数据库，安装位置
  数据、翻译和供交叉构建使用的 pkg-config 文件。生成器原生字节序
  与 x86_64 目标匹配；配方对不匹配的构建机字节序明确报错。
- libgweather 新增数据包依赖，保留交叉 introspection 补丁。新增补丁用
  pkg-config 的 prefix override 保持运行时数据库路径为
  `/usr/lib/gweather-locations/Locations.bin`，避免写入构建机 staging 路径。
- Node 新增 glibc 和 libatomic 依赖。npm/npx 保留；Corepack 按上游
  Node 25+ 的行为不再捆绑，只有上游归档实际包含它时才创建链接。
  本次没有另行引入独立 Corepack 包。
- SPICE 重写原有 GTK 后端探测补丁，继续按 GTK 是否包含 X11 后端
  决定 X11/VA-X11 探测，保留 GL 重连补丁。升级
  `feeds/packages/libs/spice-protocol` 到新版本要求的 0.14.5，声明
  spice-common 实际使用的 libudev 依赖；沿用本树 systemd 的 libudev
  provider，不新增 provider 或改变 systemd/procd 架构。
- EDS 的 libedataserver SONAME 从 27 升至 28，libcamel 从 67 升至 68。
  构建中确认 GNOME Shell 日历服务是旧 .27 的实际消费者，因而递增
  GNOME Shell release 并重建。新日历服务 NEEDED 指向 .28，目标动态
  加载器能够解析其全部依赖。
- 相关 GNOME 源码目录索引更新到已审查分支；其余包继续按现有
  series/major 策略追踪。Flatpak、GTK 3、GCR 3、IBus 和 Intel 驱动
  保留审查结论中的版本。

## 完成的验证

- 七项升级、新增数据包、SPICE 协议头文件及 GNOME Shell 重建均通过。
  Pyparsing 的 host 安装实际导入报告 3.3.3。
- 八个目标 APK 均使用本地构建公钥验证成功，新版本排序均高于旧版。
- 新增 `scripts/tests/test-custom-branch-upgrade.py` 的四项测试通过：
  - 使用目标加载器/目标库运行 Node 26 Lithium（ABI 147）和 npm；
  - 在 GJS 中加载 AT-SPI、Xdp、GWeather、EDS/ECal 和 SPICE typelibs，
    确认进程实际映射 EDS SONAME 28，并从新数据库查到 WSSS；
  - 检查日历服务链接 .28 并通过目标加载器依赖解析；
  - 检查默认天气数据库路径及构建机前缀泄漏。
- 43 项 custom 更新器测试和 2 项 APK 源码版本测试通过，共 49 项。
- 严格 Kconfig 检查通过，输出写入独立文件。custom/packages 索引和
  包元数据已刷新；新数据包可由 libgweather 的依赖自动选择。
- 原始 `.config`、390 个受保护文件（允许本次修改更新注册表）、
  所有仓库 HEAD、暂存区和 stash 状态验证通过。主仓库与 packages
  feed 的改动保持各自独立，未暂存或提交。

验证命令：

```sh
make -j6 package/custom/python-pyparsing/host/compile package/custom/at-spi2-core/compile package/custom/libportal/compile V=s
make -j6 CONFIG_PACKAGE_gweather-locations=m package/custom/gweather-locations/compile package/custom/libgweather/compile package/custom/evolution-data-server/compile package/custom/node-bin/compile package/custom/spice-gtk/compile V=s
make -j6 CONFIG_PACKAGE_gweather-locations=m package/custom/spice-gtk/compile package/custom/gnome-shell/compile V=s
python3 scripts/tests/test-custom-branch-upgrade.py
python3 scripts/tests/test-custom-package-updates.py
python3 scripts/tests/test-apk-source-versions.py
```

`CONFIG_PACKAGE_gweather-locations=m` 是为保留现有 `.config` 而使用的
临时构建选项；之后正常执行配置归一化时，已选中的 libgweather 会选择
该运行时数据依赖。本次独立 Kconfig 检查也验证了这一关系。

本地冒烟测试不等同于设备上的 GNOME 会话、辅助功能、portal 对话框、
日历 D-Bus 服务和 SPICE 连接/GL 重连验收；未执行新固件完整构建或部署。

证据与备份：`.git/pull-preserve/20261029T161428Z`；签名与保护检查见 `upgrade-final-verification.json`。
