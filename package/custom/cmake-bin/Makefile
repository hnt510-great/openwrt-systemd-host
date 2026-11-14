include $(TOPDIR)/rules.mk

PKG_NAME:=cmake-bin
# Updated by package/custom/scripts/update-prebuilt-packages.sh.
PKG_VERSION:=4.5.0
PKG_VERSION_MAJOR:=$(word 1,$(subst ., ,$(PKG_VERSION))).$(word 2,$(subst ., ,$(PKG_VERSION)))
PKG_RELEASE:=1

PKG_SOURCE:=cmake-$(PKG_VERSION)-linux-x86_64.tar.gz
PKG_SOURCE_URL:=https://github.com/Kitware/CMake/releases/download/v$(PKG_VERSION)/
PKG_HASH:=81f0d5b0960fb6adc8197030ffc827fba937640d51e73e39e0e9e40d88c66f6f

PKG_BUILD_DIR:=$(BUILD_DIR)/cmake-$(PKG_VERSION)-linux-x86_64

PKG_LICENSE:=BSD-3-Clause
PKG_LICENSE_FILES:=doc/cmake/LICENSE.rst

include $(INCLUDE_DIR)/package.mk

define Package/cmake-bin
  SECTION:=devel
  CATEGORY:=Development
  TITLE:=CMake pre-compiled binaries (glibc x86_64)
  URL:=https://cmake.org/
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +libpthread +librt
  PKGARCH:=x86_64
endef

define Package/cmake-bin/description
  Official pre-compiled CMake command-line tools for Linux x86_64.
  This package requires an x86_64 target using glibc.
endef

define Build/Compile
endef

define Package/cmake-bin/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/bin/cmake $(1)/usr/bin/
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/bin/ccmake $(1)/usr/bin/
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/bin/cpack $(1)/usr/bin/
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/bin/ctest $(1)/usr/bin/

	$(INSTALL_DIR) $(1)/usr/share
	$(CP) $(PKG_BUILD_DIR)/share/cmake-$(PKG_VERSION_MAJOR) $(1)/usr/share/
endef

$(eval $(call BuildPackage,cmake-bin))
