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
