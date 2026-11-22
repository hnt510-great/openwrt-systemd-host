include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kservice
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kservice-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=c33a5bcd2ce154e275ef9445901a2813c24943e24eaf2382d24865717892353c
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Service
KF6_DEPENDS:=+qt6base-xml +kf6-kconfig +kf6-kcoreaddons +kf6-ki18n

# KService's CMakeLists rejects an in-source build, which is how OpenWrt
# normally drives CMake; give it a separate build subdirectory.
CMAKE_BINARY_SUBDIR:=build

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
