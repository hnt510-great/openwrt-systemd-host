include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kconfigwidgets
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kconfigwidgets-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=5c5e8dc7e986d85c3602b8a52b8d8909f91e7433ecad8037099491250f5f4e36
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Config Widgets
KF6_DEPENDS:=+qt6base-widgets +qt6base-dbus +kf6-kcoreaddons +kf6-kcodecs \
	+kf6-kconfig +kf6-kguiaddons +kf6-ki18n +kf6-kwidgetsaddons +kf6-kcolorscheme
KF6_CMAKE_OPTIONS:=-DUSE_DBUS=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
