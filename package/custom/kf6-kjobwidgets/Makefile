include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kjobwidgets
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kjobwidgets-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=393b6eb6b35d680d48a5c7b09359668bddc1ed89d4fa70b8a8a81fb2d841ce7a
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Job Widgets
KF6_DEPENDS:=+qt6base-widgets +qt6base-dbus +kf6-kcoreaddons +kf6-kwidgetsaddons \
	+kf6-knotifications
KF6_CMAKE_OPTIONS:=-DUSE_DBUS=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
