# SPDX-License-Identifier: GPL-2.0-only

include $(TOPDIR)/rules.mk

PKG_NAME:=native-libs-dev
PKG_VERSION:=1
PKG_RELEASE:=2

# Export only target development files; never copy host staging or the whole
# target sysroot. Runtime libraries remain owned by their original packages.
NATIVE_DEV_HEADERS:= \
	openssl curl json-c mbedtls psa nghttp2 readline uuid lzma libpng16 \
	sqlite3.h sqlite3ext.h ffi.h ffitarget.h pcre2.h pcre2posix.h \
	bzlib.h lzma.h zstd.h zstd_errors.h png.h pngconf.h pnglibconf.h \
	jconfig.h jerror.h jmorecfg.h jpeglib.h expat.h expat_external.h gmp.h \
	sodium sodium.h seccomp.h seccomp-syscalls.h libelf.h gelf.h nlist.h \
	lz4.h lz4hc.h lz4frame.h lz4frame_static.h zip.h zipconf.h \
	pcap pcap.h pcap-bpf.h pcap-namedb.h event2 event.h evutil.h \
	libmnl libnl3 systemd libubox libubus.h ubusmsg.h ubus_common.h \
	uci.h uci_config.h uci_blob.h

# The other unversioned library names are already supplied by runtime packages.
NATIVE_DEV_LINKS:= \
	libssl.so libcrypto.so libcurl.so libsqlite3.so libjson-c.so libffi.so \
	libbz2.so liblzma.so libexpat.so libuuid.so libgmp.so \
	libmbedtls.so libmbedcrypto.so libmbedx509.so libnghttp2.so \
	libsodium.so libseccomp.so libelf.so liblz4.so libzip.so libpcap.so \
	libevent_core.so libmnl.so libnl-3.so libnl-route-3.so libsystemd.so \
	libubox.so libubus.so libuci.so libblobmsg_json.so libjson_script.so

NATIVE_DEV_PC:= \
	openssl libcrypto libssl libcurl sqlite3 json-c libffi \
	libpcre2-8 libpcre2-posix liblzma libzstd libpng libpng16 libjpeg \
	expat readline uuid gmp mbedtls mbedcrypto mbedx509 libnghttp2 \
	libsodium libseccomp libelf liblz4 libzip libpcap libevent_core \
	libmnl libnl-3.0 libnl-route-3.0 libsystemd

NATIVE_DEV_OPENWRT_LIBS:=libubox libubus libuci libblobmsg-json libjson-script

# Repackage when the exported headers or metadata change, including after a
# dependency update with an unchanged ABI. Keep these paths out of host staging.
PKG_FILE_DEPENDS:= \
	$(addprefix $(STAGING_DIR)/usr/include/,$(NATIVE_DEV_HEADERS)) \
	$(addprefix $(STAGING_DIR)/usr/lib/,$(NATIVE_DEV_LINKS)) \
	$(addprefix $(STAGING_DIR)/usr/lib/pkgconfig/,$(addsuffix .pc,$(NATIVE_DEV_PC))) \
	$(addprefix $(STAGING_DIR)/pkginfo/,$(addsuffix .version,$(NATIVE_DEV_OPENWRT_LIBS)))

include $(INCLUDE_DIR)/package.mk

define Package/native-libs-dev
  SECTION:=devel
  CATEGORY:=Development
  SUBMENU:=Libraries
  TITLE:=Common library headers for native C/C++ development
  DEPENDS:=+gcc +make +pkgconf +zlib-dev +libncurses-dev +libxml2-dev \
	+libopenssl +libcurl +libsqlite3 +libjson-c +libffi +libpcre2 \
	+libbz2 +liblzma +libzstd +libpng +libjpeg-turbo +libexpat \
	+libreadline +libuuid +libgmp +libmbedtls +libnghttp2 \
	+libsodium +libseccomp +libelf +liblz4 +libzip-gnutls +libpcap \
	+libevent2-core +libmnl +libnl-core +libnl-route +libsystemd \
	+libubox +libubus +libuci +libblobmsg-json +libjson-script
endef

define Package/native-libs-dev/description
  Target-built headers, shared-library linker names and pkg-config metadata
  for OpenSSL, curl, SQLite, JSON-C, libffi, PCRE2 (8-bit/POSIX), bzip2, XZ,
  Zstandard, PNG, JPEG, Expat, readline, UUID, GMP, Mbed TLS and nghttp2.
  Also includes libsodium, seccomp, libelf, LZ4, libzip, pcap, libevent core,
  libmnl, libnl core/route, libsystemd, and OpenWrt ubus/ubox/UCI libraries.
  Also selects the existing zlib, ncurses and libxml2 development packages.
  Intended for native dynamic linking; static third-party archives are omitted.
endef

define Build/Compile
endef

define Package/native-libs-dev/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(LN) pkgconf $(1)/usr/bin/pkg-config
	$(CP) $(addprefix $(STAGING_DIR)/usr/include/,$(NATIVE_DEV_HEADERS)) $(1)/usr/include/
	$(CP) $(addprefix $(STAGING_DIR)/usr/lib/,$(NATIVE_DEV_LINKS)) $(1)/usr/lib/
	$(INSTALL_DATA) $(addprefix $(STAGING_DIR)/usr/lib/pkgconfig/,$(addsuffix .pc,$(NATIVE_DEV_PC))) $(1)/usr/lib/pkgconfig/
	# Remove cross-build search paths from metadata used on the device.
	$(SED) 's,$(STAGING_DIR),,g;s,-[IL]$(TOOLCHAIN_DIR)/usr/lib,,g;s,-[IL]$(TOOLCHAIN_DIR)/lib,,g' $(1)/usr/lib/pkgconfig/*.pc
	# These OpenWrt libraries do not export upstream pkg-config files. Use the
	# staged ABI version and declare the public header/link dependencies.
	for package in $(NATIVE_DEV_OPENWRT_LIBS); do \
		name=$$$$package; requires=; \
		case $$$$package in \
			libubus|libuci) requires=libubox;; \
			libblobmsg-json) name=libblobmsg_json; requires='libubox json-c';; \
			libjson-script) name=libjson_script; requires=libubox;; \
		esac; \
		version=$$$$(cat $(STAGING_DIR)/pkginfo/$$$$package.version); \
		test -n "$$$$version" || exit 1; \
		printf '%s\n' 'prefix=/usr' 'libdir=$$$${prefix}/lib' \
			'includedir=$$$${prefix}/include' '' "Name: $$$$name" \
			"Description: OpenWrt $$$$name development library" \
			"Version: $$$$version" "Requires: $$$$requires" \
			'Libs: -L$$$${libdir} -l'$$$${name#lib} \
			'Cflags: -I$$$${includedir}' \
			> $(1)/usr/lib/pkgconfig/$$$$name.pc; \
	done
	! grep -r -F '$(TOPDIR)/' $(1)/usr/lib/pkgconfig
endef

$(eval $(call BuildPackage,native-libs-dev))
