include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kservice
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kservice-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=495545ac7120305e3c13d5d1c7760c5607527db5816c6ceedf8c9a623b051e2e
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Service
KF6_DEPENDS:=+qt6base-xml +kf6-kconfig +kf6-kcoreaddons +kf6-ki18n

# KService's CMakeLists rejects an in-source build, which is how OpenWrt
# normally drives CMake; give it a separate build subdirectory.
CMAKE_BINARY_SUBDIR:=build

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
