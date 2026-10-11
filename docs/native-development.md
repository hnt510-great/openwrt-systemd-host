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
