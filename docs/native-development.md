# 在固件上编译 C/C++ 程序

在 `make menuconfig` 的 **Development → Libraries** 中启用
`native-libs-dev`。它使用当前 OpenWrt 目标构建的开发文件，并自动选择
GCC/G++、make、pkgconf、运行库及已有的 zlib、ncurses、libxml2 开发包。

提供的第三方库包括 OpenSSL、curl、SQLite、JSON-C、libffi、PCRE2
（8 位和 POSIX 接口）、bzip2、XZ/liblzma、Zstandard、PNG、JPEG、
Expat、readline、UUID、GMP、Mbed TLS 和 nghttp2。
头文件位于 `/usr/include`，链接名称位于 `/usr/lib`，pkg-config 元数据
位于 `/usr/lib/pkgconfig`。运行库仍由各自的 OpenWrt 包管理。
同时提供 `pkg-config` 命令，调用镜像中的 `pkgconf`。

另提供 libsodium、libseccomp、libelf、LZ4、libzip、libpcap、libevent
core、libmnl、libnl core/route、libsystemd，以及 OpenWrt 的 libubox、
libubus、libuci、libblobmsg_json、libjson_script 开发文件。
对应模块名为 `libsodium`、`libseccomp`、`libelf`、`liblz4`、`libzip`、
`libpcap`、`libevent_core`、`libmnl`、`libnl-3.0`、`libnl-route-3.0`、
`libsystemd`、`libubox`、`libubus`、`libuci`、`libblobmsg_json`、
`libjson_script`。OpenWrt 库的 pkg-config 版本使用本次构建的 ABI 日期。
libevent 提供 core API，libnl 提供 core/route API；其他组件按需安装。

在刷入新固件后，直接编译并运行：

```sh
cat > hello.c <<'EOF'
#include <stdio.h>
#include <sqlite3.h>
#include <openssl/crypto.h>
int main(void)
{
    printf("SQLite: %s\nOpenSSL: %s\n",
           sqlite3_libversion(), OpenSSL_version(OPENSSL_VERSION));
    return 0;
}
EOF
gcc -Wall -Wextra hello.c -o hello $(pkg-config --cflags --libs sqlite3 openssl)
./hello
```

其他常用模块名：`libcurl`、`json-c`、`libffi`、`libpcre2-8`、
`liblzma`、`libzstd`、`libpng`、`libjpeg`、`expat`、`readline`、
`uuid`、`gmp`、`mbedtls`、`libnghttp2`、`libxml-2.0`、`zlib`。
bzip2 没有上游 pkg-config 文件，使用 `#include <bzlib.h>` 和 `-lbz2`。
使用 PCRE2 时在包含 `pcre2.h` 前定义 `PCRE2_CODE_UNIT_WIDTH 8`。

此包支持动态链接；不打包这些第三方库的静态 `.a` 文件，也不提供
`pkg-config --static` 的完整依赖闭包。CMake 可以使用 `FindOpenSSL`、
`FindCURL` 等内置模块，或 `FindPkgConfig`。修改构建树不会改变旧镜像，
需要重新构建镜像后刷入，或在匹配的固件中安装生成的 APK 包。

## 原生应用依赖与 Cockpit

`native-libs-dev 1-r3` 补齐 Cockpit 源码编译遇到的开发文件：GLib/GIO
（包括 `gio-unix-2.0` 和 `glibconfig.h`）、JSON-GLib、GnuTLS、
Nettle/Hogweed、PAM、libcrypt 和 Kerberos。另补充 libtasn1/com_err、
libcap、libattr/libacl、D-Bus、libuv、YAML、XSLT/EXSLT、libusb 和
libarchive，作为常见应用的开发依赖。

开发文件均来自当前目标构建，与运行库一同通过 APK feeds 分发，安装到
`/usr`。不再需要把头文件、链接桩和 `.pc` 手工复制到 `/usr/local`。
运行库仍归各自的包所有；PAM 已有的 `.pc` 和链接名不会重复打包。
`libcrypt.pc` 使用 glibc 兼容版 libcrypt 的元数据，不使用只含部分算法的
内部 `libxcrypt` 静态构建。GnuTLS 的 `Requires.private: nettle, hogweed`
保留，通过一起提供对应开发文件满足依赖。

新增可单独安装的包：

| APK | 内容 |
| --- | --- |
| `glib2-build-tools` | 目标机版 `gdbus-codegen`、codegen Python 模块、`glib-mkenums`、`glib-genmarshal`、`glib-compile-resources` 等；依赖运行时 schema 工具及所需 Python 模块 |
| `krb5-dev` | Kerberos 头文件、`.pc`、原生 `krb5-config`；运行库由 `krb5-libs` 提供 |
| `libcomerr-dev` | Kerberos 公共头文件需要的 `et/com_err.h`、链接名和 `.pc`，由 `krb5-dev` 自动选择 |
| `gettext-tools` | `msgfmt`、`msgmerge`、`xgettext` 等翻译工具、私有共享库和 ITS 数据，支持 `msgfmt --xml` |
| `native-build-deps` | `native-libs-dev`、上述工具以及 Autoconf/Automake/Libtool、CMake、Flex/Bison、Python/pip/setuptools、常用 shell/归档工具的依赖集合 |
| `cockpit-runtime-deps` | 为源码安装的 Cockpit 保留 systemd、GLib、JSON-GLib、GnuTLS、Kerberos、PAM、libcrypt、Python 和 CA 运行依赖；不包含 Cockpit 本体 |

`native-build-deps 1-r2` 要求 `native-libs-dev >= 1-r3`，因此已安装旧开发包
的设备也会升级到包含新头文件的版本。已使用物理设备安装前的 APK 数据库
验证：普通 `apk add native-build-deps cockpit-runtime-deps` 即会选择此升级。

GLib 的交叉编译 `.pc` 仍保留构建主机工具路径；只有安装到设备的副本改回
`${bindir}`，避免破坏交叉构建。Kerberos 的交叉编译 `krb5-config` 同样不变，
开发包使用原始目标版脚本。Kerberos 构建传入 `WARN_CFLAGS=`，避免 GCC 14
触发上游的警告即错误策略。

独立 packages feed 的改动导出到
`patches/feeds/0016-packages-native-app-deps.patch`，基准记录在
`configs/native-app-build-feeds.json`；当前工作树已应用，不要重复应用。

构建主机可合并 `configs/native-app-build.config`，再生成配置和编译：

```sh
make defconfig
scripts/config/conf --fatalrecursive --defconfig=.config -w .config Config.in
make -j6 package/custom/native-build-deps/compile package/custom/cockpit-runtime-deps/compile V=s
./scripts/publish-changed-feeds.sh --dry-run
./scripts/publish-changed-feeds.sh
```

严格 Kconfig 检查失败时应先解决报告的问题，不能把普通 `make defconfig`
的成功当作严格检查通过。包发布流程见 [本地 APK feeds](lan-apk-feeds.md)。
发布会处理当前输出中的所有变更，先审阅 dry-run；只供已完成且 ABI 匹配的
构建使用，包编译本身不会发布或在远端安装。

设备使用自身 ABI 对应的本地 feeds：

```sh
sudo apk update
sudo apk add --simulate native-build-deps
sudo apk add native-build-deps
sudo apk add --simulate cockpit-runtime-deps
sudo apk add cockpit-runtime-deps
sh /path/to/test-native-app-deps.sh
```

验证脚本为仓库的 `scripts/test-native-app-deps.sh`，会真正编译和运行
库调用、生成 D-Bus C 代码、编译 GLib resource，并执行 gettext XML 翻译。
`native-libs-dev` 是库开发文件集合，`native-build-deps` 额外安装常用工具；
项目专属的 Node/npm、Meson/Ninja 或测试工具仍需按项目要求准备。

### 从远端手工安装迁移

先记录 `apk info`、`/usr/local` 安装清单及 Cockpit 的构建环境。
APK 不接管或删除已有 `/usr/local` 文件。安装开发 APK 后，重新配置源码
构建时使用系统路径，例如：

```sh
export PATH=/usr/bin:/usr/sbin:/bin:/sbin
unset PKG_CONFIG_PATH PKG_CONFIG_SYSROOT_DIR CPPFLAGS CFLAGS CXXFLAGS LDFLAGS
export PKG_CONFIG_LIBDIR=/usr/lib/pkgconfig:/usr/share/pkgconfig
pkg-config --modversion gio-unix-2.0 json-glib-1.0 gnutls krb5-gssapi pam libcrypt
pkg-config --variable=gdbus_codegen gio-2.0
krb5-config --prefix
```

预期工具位于 `/usr/bin`，Kerberos prefix 为 `/usr`，不再加入
`-Wl,-rpath,/usr/local/lib`。新构建应在新的构建目录重新 configure，
避免复用旧依赖探测缓存。验证新二进制的动态依赖及实际加载路径后，再按
原安装清单处理旧副本，尤其是 `/usr/local/lib/libkrb5*`；不要批量删除
`/usr/local` 或依靠 `--force-overwrite` 解决冲突。

Cockpit 本体目前仍是远端源码安装，本次依赖包不会重装或切换 Cockpit，
也不调整其 PAM、证书、监听地址或 systemd 单元。`po/LINGUAS` 属于源码
准备；Python 安装路径、`pam_systemd` 会话以及 vendored `systemd_ctypes`
缓存修复属于 Cockpit 安装/运行问题，不能用安装 C 库开发包代替处理。
继续保留已验证的远端修复；动态 socket 用户/组交给其 systemd 单元创建。
`cockpit-runtime-deps` 会作为 APK world 中的运行依赖入口，避免以后移除
构建工具时把源码安装的 Cockpit 所需库当作孤立依赖一起删除。它只管理
APK 安装的系统库；只有新构建实际使用这些系统库后，才完成从旧
`/usr/local` 库的迁移。

### 2026-10-18 验证

上述新增包与 `native-libs-dev 1-r3` 均已完成构建。使用当前公钥验证签名的
临时 APK 仓库，从空的 usr-merge 根目录模拟并安装 `native-build-deps`、
`cockpit-runtime-deps` 和 `base-files`，共 229 个包、384.4 MiB，无文件归属
冲突。安装脚本和服务 hook 被禁用，仅在隔离目录应用包声明的 alternatives。
通过用户命名空间/chroot 执行目标 x86_64/glibc 工具，新增库的实际编译、
链接和运行、GLib 代码生成及 gettext XML 翻译全部通过。

本地 LAN 发布 dry-run 通过，识别 17 个变更包、3 个仓库，内核频道保持不变；
没有执行发布或远端安装。严格 Kconfig 检查仍被既有的 dnsmasq-full、
fwknopd、gensio 循环依赖阻挡，修改前后报告的相关符号完全一致。
此验证不是 QEMU 启动或物理设备/Cockpit 登录验证。
日志、APK 哈希及重现脚本保存在
`/srv/openwrt-validation/native-app-deps-validation-20261018/`。

### 2026-10-18 发布与物理设备迁移

已发布对应 ABI `6.18.55~1e6d3a41204c57acfef0c7a584b7cc0e-r1` 的依赖包。
第一次发布更新 17 个包，随后单独发布最低版本约束修复
`native-build-deps 1-r2`。最终快照为 `20261018T121405.098015Z`，
内核频道保持原 G18，未发布新内核代际。

物理路由器通过既有信任密钥刷新 feeds、模拟安装后完成安装。相对安装前
新增 8 个包，升级 4 个包；`native-libs-dev` 从 `1-r2` 升到 `1-r3`。
设备上实际运行 `scripts/test-native-app-deps.sh`，库调用、代码生成及 XML
翻译全部通过。

旧 Cockpit 的 `cockpit-session` 依赖本地 `libcom_err.so.3`，而 APK 提供
`libcom_err.so.0`，因此没有直接删除旧库。使用 APK 开发文件，在
`/home/desktop-user/cockpit-build/apk-cockpit-369/` 重新配置和编译 Cockpit 369，
再替换 5 个 C 程序：`cockpit-session`、`cockpit-tls`、`cockpit-ws`、
`cockpit-wsinstance-factory`、`cockpit-certificate-ensure`。均无 RPATH/RUNPATH，
动态依赖解析至系统库；运行中的 Cockpit 进程映射也确认不再加载
`/usr/local/lib`。现有 Python bridge、60 个 Python 源文件、`.pth` 和
vendored D-Bus 缓存修复保留。

与 APK 重复的 64 项开发文件已移到备份目录，避免编译器优先使用旧头文件。
旧版 Kerberos 命令所需的版本化本地运行库继续保留。远端
`build-cockpit.sh` 已改为使用系统工具和 pkg-config，构建 5 个 C 程序并
检查依赖；`APK-MIGRATION.md` 记录当前用法。

Cockpit socket 已重启，仍只监听 `192.0.2.1:9090`。HTTPS 返回 200、
证书校验成功；无凭据的 `/cockpit/login` 返回预期的 401。重复连接不存在
的用户 D-Bus 未污染缓存，系统 D-Bus 连接正常。未使用账号密码进行浏览器
登录验证。PAM、证书、监听配置、网络、防火墙、DHCP、GRUB、内核状态及
boot ID 的前后核对均未改变；没有重启路由器。

远端回退文件保存在 `/root/native-app-deps-migration-20261018/`，包括
安装前 `/usr/local` 和配置归档、APK 数据库/world、原始脚本、被移走的
开发文件清单，以及原来的 5 个 C 程序。构建和部署证据保存在本机
`/srv/openwrt-validation/native-app-deps-deployment-20261018/`。

仓库的 `scripts/test-native-libs.sh` 可以复制到设备后用 `sh` 执行。
它在临时目录中验证所有列出的库及头文件、C/C++ 动态链接、线程、
程序运行，以及 CMake/pkg-config 构建；CMake 检查需要安装 `cmake-bin`。

2026-10-11 已在当前 x86_64/glibc/systemd EFI 镜像的全新 QEMU/KVM
启动环境中通过此脚本：GCC/G++ 14.4.0 编译运行、C++ 线程与容器、
各库的动态链接（包括 ncurses），以及 CMake 构建均通过。
扩展版本 `native-libs-dev 1-r2` 的新增 16 个库接口也通过了独立 C
程序与 CMake 构建运行检查，包括 LZ4 压缩往返、Netlink 对象和
socket、systemd API、UCI 上下文以及 libubox JSON 处理。
镜像 SHA256 校验和开发包 APK 签名校验通过；未刷写实际设备。

## 解析器和内核构建工具

当前桌面镜像配置还选择 `flex`、`bison`、`bc` 和 `pahole`。
其他配置可以合并 `configs/native-build-tools.config` 后运行
`make defconfig`。`bison` 包包含 `/usr/share/bison` 的 skeleton 和 m4
数据，并依赖 `m4`；运行时使用 `/usr/bin/m4`，因此设备上可以直接
生成 C/C++ 解析器，不会引用宿主 staging 路径。

`package/devel/pahole` 是目标包，与 `tools/dwarves` 的宿主构建分开。
它复用宿主包的 dwarves 1.31 源码和校验和，支持当前 glibc 固件，
动态使用目标 `libdw`、`libelf`、`libbpf` 和 zlib；私有 dwarves 库链接
到命令中。它依赖 `binutils`，默认使用 `/usr/bin/objcopy` 添加 BTF
段，保留上游 `LLVM_OBJCOPY` 环境变量覆盖。它可检查 DWARF 结构
布局并生成内核构建使用的 BTF。
上游构建选项见 [dwarves README](https://github.com/acmel/dwarves/tree/v1.31)。

独立 packages feed 的 Bison 修复保存在
`patches/feeds/0006-packages-bison-native-data.patch`，基于 feed 提交
`a551dd96e41ecfcdae329bafb8c79466abaa45ce`。提交与来源记录在 `configs/native-build-tools-feeds.json`。当前 feed 已应用此修改，
不要重复应用。窄范围构建命令为：

```sh
make -j8 package/feeds/packages/flex/compile \
  package/feeds/packages/bison/compile package/feeds/packages/bc/compile \
  package/devel/pahole/compile V=s
```

在匹配的设备上运行 `sh scripts/test-native-build-tools.sh`，验证实际
lexer/parser 生成、编译和运行，bc 小数运算，以及 DWARF/BTF 往返。
该检查需要已有的 GCC 和 readelf，仅使用自动清理的临时目录。

2026-10-13 的镜像和物理设备检查结果见
[构建工具验证记录](native-build-tools-validation.md)。


## Mainline x86_64 kernel builds

`configs/native-build-tools.config` now includes GCC/binutils/make, the
`native-libs-dev` headers and linker metadata, Bash, Git with HTTPS and CA
certificates, Perl with File/Getopt modules, Python, awk, and compression tools.
The desktop profile already selects these dependencies. Kernel host tools use
libc, libelf/gelf, OpenSSL and zlib development files from the target packages;
the kernel's own internal headers come from the cloned kernel source.

The [upstream build requirements](https://docs.kernel.org/process/changes.html)
describe configuration-dependent tools such as Rust, LLVM, and pahole.

Native GCC release 8 restores the upstream `limitx.h + glimits.h + limity.h`
wrapper during packaging. Cross-building native GCC can otherwise leave only
its integer limits in `<limits.h>`, hiding glibc/POSIX `PATH_MAX`, `NAME_MAX`,
and `MB_LEN_MAX`. This causes Kconfig compilation to fail before defconfig.
The feed change is exported in
`patches/feeds/0010-packages-gcc-native-limits.patch`; its base is recorded in
`configs/native-kernel-build-feeds.json`. It is already applied locally.

Use a writable build disk with at least 20 GiB free, rather than `/tmp` or the
firmware's small overlay. For a 12-vCPU VM with 10 GiB RAM:

```sh
cd /srv/kernel-build
git clone --depth=1 https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git linux
cd linux
git rev-parse HEAD
make -j12 ARCH=x86_64 x86_64_defconfig
make -j12 ARCH=x86_64
```

The build produces `arch/x86/boot/bzImage`, `vmlinux`, `System.map`, and kernel
modules. Building these artifacts does not install the new kernel or replace
the running OpenWrt kernel. An unmodified x86_64 defconfig disables Rust and
BTF; the existing pahole smoke check separately exercises BTF generation.
See [native kernel build validation](native-kernel-build-validation.md) for
the tested commit, actual missing dependencies, and final-image acceptance.
