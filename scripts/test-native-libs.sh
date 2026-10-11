#!/bin/sh
# Run on the target image to verify native headers, linking and library loading.
set -eu

work_dir=$(mktemp -d /tmp/native-libs-test.XXXXXX)
trap 'rm -rf "$work_dir"' EXIT HUP INT TERM
cd "$work_dir"

modules='openssl libcurl sqlite3 json-c libffi libpcre2-8 libpcre2-posix
liblzma libzstd libpng libjpeg expat readline uuid gmp mbedtls libnghttp2
libxml-2.0 zlib ncursesw'
pkg-config --exists $modules
pkg-config --modversion $modules

cat > smoke.c <<'EOF'
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <openssl/crypto.h>
#include <curl/curl.h>
#include <sqlite3.h>
#include <json-c/json.h>
#include <ffi.h>
#define PCRE2_CODE_UNIT_WIDTH 8
#include <pcre2.h>
#include <pcre2posix.h>
#include <bzlib.h>
#include <lzma.h>
#include <zstd.h>
#include <png.h>
#include <jpeglib.h>
#include <expat.h>
#include <readline/readline.h>
#include <uuid/uuid.h>
#include <gmp.h>
#include <mbedtls/version.h>
#include <mbedtls/ssl.h>
#include <nghttp2/nghttp2.h>
#include <libxml/parser.h>
#include <zlib.h>
#include <curses.h>

int main(void)
{
    sqlite3 *db = NULL;
    struct json_object *obj = json_tokener_parse("{\"native\":true}");
    ffi_cif cif;
    regex_t regex;
    struct jpeg_error_mgr jpeg_error;
    XML_Parser parser = XML_ParserCreate(NULL);
    uuid_t id;
    mpz_t number;
    mbedtls_ssl_context tls;
    int error;
    PCRE2_SIZE offset;
    pcre2_code *pattern = pcre2_compile((PCRE2_SPTR)"native", PCRE2_ZERO_TERMINATED,
                                       0, &error, &offset, NULL);
    if (!obj || !parser || !pattern ||
        sqlite3_open(":memory:", &db) != SQLITE_OK ||
        curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK ||
        ffi_prep_cif(&cif, FFI_DEFAULT_ABI, 0, &ffi_type_void, NULL) != FFI_OK ||
        regcomp(&regex, "native", REG_EXTENDED) != 0)
        return 1;
    uuid_generate(id);
    mpz_init_set_ui(number, 42);
    if (mpz_cmp_ui(number, 42) != 0 || uuid_is_null(id))
        return 2;
    jpeg_std_error(&jpeg_error);
    mbedtls_ssl_init(&tls);
    xmlInitParser();
    printf("%s\ncurl %s; SQLite %s; JSON-C %s\n", OpenSSL_version(OPENSSL_VERSION),
           curl_version(), sqlite3_libversion(), json_c_version());
    printf("bzip2 %s; XZ %s; Zstd %s; PNG %s; Expat %s\n",
           BZ2_bzlibVersion(), lzma_version_string(), ZSTD_versionString(),
           png_get_libpng_ver(NULL), XML_ExpatVersion());
    printf("readline %s; GMP %s; %s; nghttp2 %s; libxml2 %s; zlib %s; %s\n",
           rl_library_version, gmp_version, MBEDTLS_VERSION_STRING_FULL,
           nghttp2_version(0)->version_str, xmlParserVersion,
           zlibVersion(), curses_version());
    regfree(&regex);
    pcre2_code_free(pattern);
    mpz_clear(number);
    XML_ParserFree(parser);
    json_object_put(obj);
    sqlite3_close(db);
    curl_global_cleanup();
    mbedtls_ssl_free(&tls);
    xmlCleanupParser();
    puts("native C library smoke test passed");
    return 0;
}
EOF

gcc -Wall -Wextra -Werror smoke.c -o smoke $(pkg-config --cflags --libs $modules) -lbz2
./smoke
if command -v objdump >/dev/null 2>&1; then
    objdump -p smoke | grep 'NEEDED'
    objdump -p smoke | grep -q 'NEEDED.*libncursesw.so'
fi

cat > smoke.cpp <<'EOF'
#include <iostream>
#include <thread>
#include <vector>
int main()
{
    std::vector<int> values{1, 2, 3};
    std::thread worker([&] { values.push_back(4); });
    worker.join();
    if (values.size() != 4) return 1;
    std::cout << "native C++ thread/vector smoke test passed\n";
}
EOF
g++ -std=c++17 -Wall -Wextra -Werror -pthread smoke.cpp -o smoke-cpp
./smoke-cpp

extended_modules='libsodium libseccomp libelf liblz4 libzip libpcap
libevent_core libmnl libnl-3.0 libnl-route-3.0 libsystemd
libubox libubus libuci libblobmsg_json libjson_script'
pkg-config --exists $extended_modules
pkg-config --modversion $extended_modules
cat > extended.c <<'EOF'
#include <stdio.h>
#include <string.h>
#include <sodium.h>
#include <seccomp.h>
#include <libelf.h>
#include <lz4.h>
#include <zip.h>
#include <pcap/pcap.h>
#include <event2/event.h>
#include <libmnl/libmnl.h>
#include <netlink/socket.h>
#include <netlink/route/link.h>
#include <systemd/sd-bus.h>
#include <systemd/sd-id128.h>
#include <libubox/blobmsg_json.h>
#include <libubox/json_script.h>
#include <libubus.h>
#include <uci.h>

int main(void)
{
    char compressed[128], restored[128], id_string[SD_ID128_STRING_MAX];
    const char message[] = "native library extension";
    scmp_filter_ctx filter = seccomp_init(SCMP_ACT_ALLOW);
    zip_error_t zip_error;
    pcap_t *pcap = pcap_open_dead(DLT_EN10MB, 65535);
    struct event_base *events = event_base_new();
    struct mnl_socket *mnl = mnl_socket_open(NETLINK_ROUTE);
    struct nl_sock *nl = nl_socket_alloc();
    struct rtnl_link *link = rtnl_link_alloc();
    struct uci_context *uci = uci_alloc_context();
    struct blob_buf blob = {0};
    struct json_script_ctx json_script = {0};
    sd_bus *bus = NULL;
    sd_id128_t id;
    int size;

    if (sodium_init() < 0 || !filter || elf_version(EV_CURRENT) == EV_NONE ||
        !pcap || !events || !mnl || !nl || !link || !uci ||
        sd_bus_new(&bus) < 0 || sd_id128_randomize(&id) < 0)
        return 1;
    size = LZ4_compress_default(message, compressed, sizeof(message), sizeof(compressed));
    if (size <= 0 || LZ4_decompress_safe(compressed, restored, size, sizeof(restored)) !=
        sizeof(message) || memcmp(message, restored, sizeof(message)))
        return 2;
    blob_buf_init(&blob, 0);
    if (!blobmsg_add_json_from_string(&blob, "{\"native\":true}"))
        return 3;
    json_script_init(&json_script);
    zip_error_init(&zip_error);
    printf("libsodium %s; seccomp %u.%u.%u; LZ4 %s; libzip %s\n",
           sodium_version_string(), seccomp_version()->major,
           seccomp_version()->minor, seccomp_version()->micro,
           LZ4_versionString(), zip_libzip_version());
    printf("%s; libevent %s; systemd ID %s; ubus %s\n",
           pcap_lib_version(), event_get_version(), sd_id128_to_string(id, id_string),
           ubus_strerror(UBUS_STATUS_OK));
    zip_error_fini(&zip_error);
    json_script_free(&json_script);
    blob_buf_free(&blob);
    uci_free_context(uci);
    sd_bus_unref(bus);
    rtnl_link_put(link);
    nl_socket_free(nl);
    mnl_socket_close(mnl);
    event_base_free(events);
    pcap_close(pcap);
    seccomp_release(filter);
    puts("extended native libraries smoke test passed");
    return 0;
}
EOF
gcc -Wall -Wextra -Werror extended.c -o extended $(pkg-config --cflags --libs $extended_modules)
./extended
if command -v objdump >/dev/null 2>&1; then
    objdump -p extended | grep 'NEEDED'
fi

cat > CMakeLists.txt <<'EOF'
cmake_minimum_required(VERSION 3.16)
project(native_libraries C)
find_package(PkgConfig REQUIRED)
pkg_check_modules(NATIVE REQUIRED IMPORTED_TARGET
    openssl libcurl sqlite3 json-c libffi libpcre2-8 libpcre2-posix
    liblzma libzstd libpng libjpeg expat readline uuid gmp mbedtls
    libnghttp2 libxml-2.0 zlib ncursesw)
add_executable(smoke-cmake smoke.c)
target_link_libraries(smoke-cmake PRIVATE PkgConfig::NATIVE bz2)
pkg_check_modules(EXTENDED REQUIRED IMPORTED_TARGET
    libsodium libseccomp libelf liblz4 libzip libpcap libevent_core
    libmnl libnl-3.0 libnl-route-3.0 libsystemd libubox libubus libuci
    libblobmsg_json libjson_script)
add_executable(extended-cmake extended.c)
target_link_libraries(extended-cmake PRIVATE PkgConfig::EXTENDED)
EOF
cmake -S . -B build
cmake --build build -j2
./build/smoke-cmake
./build/extended-cmake
echo 'All native development checks passed'
