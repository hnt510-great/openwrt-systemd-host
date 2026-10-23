include $(TOPDIR)/rules.mk

PKG_NAME:=gmmlib
PKG_VERSION:=22.10.2
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/intel/gmmlib/tar.gz/intel-gmmlib-$(PKG_VERSION)?
PKG_HASH:=94d0038ef92bb65b86d08f004197c56f8d81f82f9ac7a25c202a88afd653a30b
PKG_BUILD_DIR:=$(BUILD_DIR)/gmmlib-intel-gmmlib-$(PKG_VERSION)
PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=LICENSE.md
CMAKE_BINARY_SUBDIR:=openwrt-build

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

define Package/libigdgmm
  SECTION:=libs
  CATEGORY:=Libraries
  SUBMENU:=Video
  TITLE:=Intel graphics memory management library
  URL:=https://github.com/intel/gmmlib
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +libstdcpp
endef

CMAKE_OPTIONS += -DRUN_TEST_SUITE=OFF -DCMAKE_INSTALL_LIBDIR=lib

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/igdgmm $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libigdgmm.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/igdgmm.pc $(1)/usr/lib/pkgconfig/
endef

define Package/libigdgmm/install
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/share/licenses/libigdgmm
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libigdgmm.so.* $(1)/usr/lib/
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/LICENSE.md $(1)/usr/share/licenses/libigdgmm/
endef

$(eval $(call BuildPackage,libigdgmm))
