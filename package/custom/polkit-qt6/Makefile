include $(TOPDIR)/rules.mk

PKG_NAME:=polkit-qt6
PKG_VERSION:=0.201.1
PKG_RELEASE:=1
PKG_SOURCE:=polkit-qt-1-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/polkit-qt-1/
PKG_BUILD_DIR:=$(BUILD_DIR)/polkit-qt-1-$(PKG_VERSION)
PKG_HASH:=95d8e2cae530c546d9437459deb8a1bea38d572f0f9772cc2860dc143637f256
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
CMAKE_INSTALL:=1
PKG_BUILD_DEPENDS:=qt6base/host qt6base polkit glib2

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

CMAKE_OPTIONS += \
	-DQT_MAJOR_VERSION=6 \
	-DQT_HOST_PATH="$(STAGING_DIR_HOSTPKG)" \
	-DBUILD_EXAMPLES=OFF \
	-DBUILD_TEST=OFF

define Package/polkit-qt6
  SECTION:=libs
  CATEGORY:=Libraries
  SUBMENU:=KDE Frameworks 6
  TITLE:=Qt6 wrapper for Polkit
  URL:=https://kde.org/
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +qt6base-core +qt6base-gui +qt6base-widgets +qt6base-dbus +polkit +glib2 +libstdcpp
endef

define Package/polkit-qt6/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libpolkit-qt6-*.so.* $(1)/usr/lib/
endef

$(eval $(call BuildPackage,polkit-qt6))
