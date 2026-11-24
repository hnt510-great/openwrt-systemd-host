include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kxmlgui
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kxmlgui-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=3b9be65d4f30e372bc9b77321da5a31dec9fe997a946a6a8a03b64377856ab38
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=XML GUI
KF6_DEPENDS:=+qt6base-widgets +qt6base-network +qt6base-printsupport +qt6base-dbus \
	+kf6-kcoreaddons +kf6-kitemviews +kf6-kconfig +kf6-kconfigwidgets \
	+kf6-kguiaddons +kf6-ki18n +kf6-kiconthemes +kf6-kwidgetsaddons \
	+kf6-kglobalaccel
KF6_CMAKE_OPTIONS:=-DUSE_DBUS=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
