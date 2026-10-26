include $(TOPDIR)/rules.mk

PKG_NAME:=libime
PKG_VERSION:=1.1.17
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION)_dict.tar.zst
PKG_SOURCE_URL:=https://download.fcitx-im.org/fcitx5/libime/
PKG_HASH:=3cd2703359b3080aa005a22a93400c5ebb5bdfcf3454f506a491c8343826176a
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_DEPENDS:=extra-cmake-modules
CMAKE_INSTALL:=1
include $(INCLUDE_DIR)/package.mk

include $(INCLUDE_DIR)/cmake.mk

define Package/libime
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=Chinese Pinyin engine and offline dictionaries
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +fcitx5 +boost-iostreams +libzstd +zlib +libstdcpp
endef

# Dictionary compilers run with the matching target loader, never host libc.
# Like the desktop's prebuilt development tools, this requires Linux x86_64.
CMAKE_OPTIONS += -DCMAKE_INSTALL_LIBDIR=lib -DECM_DIR=$(STAGING_DIR)/usr/share/ECM/cmake \
	-DENABLE_TEST=OFF -DENABLE_DATA=ON -DENABLE_TOOLS=ON \
	-DFCITX_INSTALL_CMAKECONFIG_DIR=$(STAGING_DIR)/usr/lib/cmake \
	-DCMAKE_CROSSCOMPILING_EMULATOR='$(TOOLCHAIN_DIR)/lib/ld-linux-x86-64.so.2;--library-path;$(PKG_BUILD_DIR)/bin:$(STAGING_DIR)/usr/lib:$(TOOLCHAIN_DIR)/lib'

define Build/Configure
	[ "$(shell uname -sm)" = "Linux x86_64" ] || { echo 'libime dictionary generation requires a Linux x86_64 build host' >&2; exit 1; }
	$(call Build/Configure/Default)
endef

define Build/InstallDev
	$(call Build/InstallDev/cmake,$(1))
	$(SED) 's|/usr/include/LibIME|$(STAGING_DIR)/usr/include/LibIME|g' $(1)/usr/lib/cmake/LibIME*/*Targets*.cmake
endef

define Package/libime/install
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/share
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libime $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/libime $(1)/usr/share/
endef
$(eval $(call BuildPackage,libime))
