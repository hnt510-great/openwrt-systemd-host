# SPDX-License-Identifier: GPL-2.0-only
#
# Copyright (C) 2026 OpenWrt.org

include $(TOPDIR)/rules.mk

PKG_NAME:=pigz
PKG_VERSION:=2.8
PKG_RELEASE:=1

PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://zlib.net/pigz
PKG_HASH:=eb872b4f0e1f0ebe59c9f7bd8c506c4204893ba6a8492de31df416f0d5170fd0

PKG_LICENSE:=Zlib
PKG_LICENSE_FILES:=README
PKG_CPE_ID:=cpe:/a:zlib:pigz

HOST_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/host-build.mk

define Host/Compile
	+$(HOST_MAKE_VARS) \
	$(MAKE) $(HOST_JOBS) -C $(HOST_BUILD_DIR) \
		CC="$(HOSTCC_NOCACHE)" \
		CFLAGS="$(HOST_CFLAGS) -O3 -Wall -Wextra -Wno-unknown-pragmas -Wcast-qual" \
		LDFLAGS="$(HOST_LDFLAGS)" \
		LIBS="-lm -lpthread $(STAGING_DIR_HOST)/lib/libz.a" \
		pigz
endef

define Host/Install
	$(INSTALL_BIN) $(HOST_BUILD_DIR)/pigz $(STAGING_DIR_HOST)/bin/pigz
endef

define Host/Clean
	$(RM) $(STAGING_DIR_HOST)/bin/pigz
endef

$(eval $(call HostBuild))
