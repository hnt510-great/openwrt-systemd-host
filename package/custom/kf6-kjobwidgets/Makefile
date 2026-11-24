include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kjobwidgets
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kjobwidgets-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=98eaee2846181b82b357067db00ac65e3bcf02c11322bb636aa6021a6eb65dd2
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Job Widgets
KF6_DEPENDS:=+qt6base-widgets +qt6base-dbus +kf6-kcoreaddons +kf6-kwidgetsaddons \
	+kf6-knotifications
KF6_CMAKE_OPTIONS:=-DUSE_DBUS=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
