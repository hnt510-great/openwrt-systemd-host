# Custom 包的上游更新

在仓库根目录使用标准 OpenWrt 流程：

```sh
./scripts/feeds update -a
./scripts/feeds install -a
make download
make -j8 V=s
```

本仓库的 `src-link custom ../package/custom` 除了刷新索引，还会在其他
选中 feeds 更新成功后检查 custom 包的上游稳定版本，修改需要升级的配方，
最后生成索引。`./scripts/feeds update custom` 只更新 custom；更新其他
指定 feed 不触发 custom 更新。其他 `src-link` 以及指向外部目录的同名
custom feed 不启用此逻辑。

上游检查需要主机提供 Python 3、curl 和 Git；仅索引模式不调用 Python 更新器。

`./scripts/feeds update -i -a` 始终只生成索引，不查询上游或修改配方。
更新流程不安装 feed 链接、不选择包、不修改 `.config`，也不构建、发布、
安装到设备或启动定时任务。具体软件源码仍由 OpenWrt 的 download/prepare
规则下载、解压并应用补丁。更新器只为新的配方下载临时源码以验证 SHA-256，
不创建另一套源码 checkout 或构建目录。

## 上游与版本策略

`configs/custom-package-updates.json` 登记全部 custom 配方，不以当前
`.config` 的选中状态筛选。新增包时必须同时登记；遗漏或失效的登记会报错。

上游来源包括 GitHub/GitLab 的发行或标签列表、官方发布目录、PyPI、
Mozilla ESR、Node.js LTS 和 SourceForge。发行列表按版本数值排序，
排除草稿、预发行和不符合格式的标签。GitHub 使用只读的
`git ls-remote --tags --refs` 获取全部标签，按维护分支筛选，不查询标签
REST API。对于按正式发行跟踪的包，仅在发现更高的候选版本时查询该标签
的发行 API，排除草稿、预发行和尚未发布的标签；已固定的版本无需扫描
发行历史。标签及 HTTP 元数据在本次进程内缓存。

- `series`：固定当前版本的前两个数字段，例如 `1.2.x`；
  `0.41` 这样的两段版本保持在这一系列。
- `major`：固定当前主版本。Firefox 保持当前 ESR，Node 保持当前 LTS 主版本。
- `stable`：用于整数和日期/年份发布序列，跟随稳定发行。
- `follow`：跟随指定基础配方的版本；相同源码的绑定同时使用基础配方的摘要。
  `glib2-gir` 跟随 `glib2`，`python3-libxml2` 跟随主树 `libxml2`。
  `libvirt` 与 `libvirt-python` 成组更新，任一成员校验失败都不写入该组。
- `local`：本地整合包或版本派生于内核/glibc 的包，保留已有版本机制。

新维护分支只报告待处理，不自动切换。维护分支不再公布时报告人工检查，
上游版本比本地旧时保留本地版本。相同版本的官方摘要变化会报错，避免
在没有审阅的情况下接受重新打包的源码。

更新器检查版本、下载并核对官方摘要；没有独立 SHA-256 的上游使用实际
HTTPS 下载的源码计算摘要，报告中明确标记为 `downloaded-https-source`。
后者不是独立的上游签名验证。版本更新同步处理固定的源码文件名、URL、
解压目录和 `PKG_HASH`，将 `PKG_RELEASE` 重置为 1。补丁、依赖、构建参数
和包的安装规则保留原样。

旧 Pagure 下载目录已经停止列出这些项目的发行包；维护清单按
[libosinfo 官方下载页](https://libosinfo.org/download/) 和
[virt-manager 官方下载页](https://virt-manager.org/download.html)
登记 GitLab/GitHub 发行来源。更新到新版本时同步更新下载 URL；同版本的
下载迁移必须校验现有固定摘要，保留原包修订号。Xorriso 排除上游使用
奇数微版本号标记的开发归档；X.Org/XCB 排除包含 `.99` 的开发版本。

## 本地修改与 OpenWrt patches

对下载得到的上游源码的修改使用 OpenWrt 原生补丁机制：

```text
package/custom/<包名>/Makefile
package/custom/<包名>/patches/001-description.patch
package/custom/<包名>/patches/002-description.patch
```

当前 `libgtk3`、`libvirt`、`virt-manager` 等已经使用此机制。默认
`Build/Patch` 在 prepare 阶段按补丁顺序应用这些修改；上游更新器不会重写
或删除补丁。升级后补丁不再适用时，原生 prepare/compile 会失败，需要
针对新版源码调整或移除已经被上游合入的补丁，再重新构建。

依赖、构建参数和安装规则属于 Makefile；本地集成脚本、配置及自研代码
保留在 `files/`、`src/`。这些不是对下载源码的差异，继续由现有包规则维护。
不要把 `build_dir` 中的临时修改当作长期保存方式。需要编辑上游源码时，
使用 `make package/custom/<包名>/prepare QUILT=1 V=s` 的 Quilt 工作流，
完成后用对应包的 `update` 目标将补丁导回配方目录。

更新器只自动改写无本地修改且受 Git 跟踪的配方；配方已暂存、已修改或
尚未跟踪时，停止并报告，保留工作区及 Git 索引。不自动提交、暂存、stash
或 reset。无关本地修改可以继续保留。`feeds update -f` 不绕过 custom 的
这一保护；其他 Git feeds 的 `-f/-r/-s` 行为仍由原有 feeds 脚本控制。

## 检查、失败和日志

只读检查不会创建更新日志或下载完整源码归档：

```sh
python3 scripts/update-custom-packages.py --check
python3 scripts/update-custom-packages.py --check --package libvirt
```

可重复指定 `--package`；指定联动包的任一成员都会包含整组。独立执行
辅助程序的 `--update` 只修改配方；随后需要运行
`./scripts/feeds update -i custom` 刷新索引。通常直接使用 feeds 入口。

检查模式返回 0 表示没有可更新/待审阅版本，1 表示存在更新或分支需要
审阅，2 表示检查错误。更新模式成功返回 0，错误返回非零。网络不可达、
API 限流、上游格式变化、摘要错误和本地修改都会明确报错。

GitHub API 仍对待升级的正式发行做验证。可通过环境变量 `GH_TOKEN` 或
`GITHUB_TOKEN` 提供已有令牌；只向 `api.github.com` 发送认证头，令牌不放入
命令行、更新报告或配方。发生 API 额度耗尽时，错误包含服务端给出的 UTC
恢复时间；不会将尚未验证的发行当作稳定版本，也不会自动长时间等待。

首个 custom 更新错误停止后续更新；此前成功的组保留，失败组不写入。
`feeds` 在更新错误后仍尝试按当前工作区生成索引，并保留失败退出状态。
如果前面的普通 feed 拉取失败，则跳过 custom 上游更新。

每次更新记录在忽略目录 `logs/custom-package-updates/<UTC 时间>/`：
`report.json` 包含来源、版本、摘要、校验方式、完成/失败状态；`before/`
保存本次改写配方的原始内容。它不是整个工作区或构建缓存的回滚点。
更新器通过 Git 目录内的锁防止自身并发运行；手动构建和编辑器不使用
该锁，请按更新完成后再构建的顺序操作。

实现验证命令：

```sh
perl -c scripts/feeds
python3 scripts/tests/test-custom-package-updates.py
python3 scripts/tests/test-firefox-updater.py
```

离线测试覆盖 feeds 接入顺序、仅索引模式、版本策略、上游摘要、联动组、
本地修改和原生补丁文件的保留。实际新版本能否编译及运行，应由后续
OpenWrt 包构建和所需运行验证确认。
