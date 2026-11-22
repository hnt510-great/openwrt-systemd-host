include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kxmlgui
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kxmlgui-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=a16fd3734112914ef50ed2666a16905d87e67954bc368725ccb1d5b2edc8f8f1
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=XML GUI
KF6_DEPENDS:=+qt6base-widgets +qt6base-network +qt6base-printsupport +qt6base-dbus \
	+kf6-kcoreaddons +kf6-kitemviews +kf6-kconfig +kf6-kconfigwidgets \
	+kf6-kguiaddons +kf6-ki18n +kf6-kiconthemes +kf6-kwidgetsaddons \
	+kf6-kglobalaccel
KF6_CMAKE_OPTIONS:=-DUSE_DBUS=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
