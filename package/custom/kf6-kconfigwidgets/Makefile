include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kconfigwidgets
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kconfigwidgets-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=9d7f60aec2c8153e944d0916852942abb7a28459146b1383f3c540e49dd3da8d
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Config Widgets
KF6_DEPENDS:=+qt6base-widgets +qt6base-dbus +kf6-kcoreaddons +kf6-kcodecs \
	+kf6-kconfig +kf6-kguiaddons +kf6-ki18n +kf6-kwidgetsaddons +kf6-kcolorscheme
KF6_CMAKE_OPTIONS:=-DUSE_DBUS=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
