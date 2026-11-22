include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-knotifyconfig
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=knotifyconfig-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=a02196e50f48dad0908656e3245d58bf03b0d39102fa92b056bee7d50b91afa7
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Notify Config
KF6_DEPENDS:=+qt6base-widgets +qt6base-dbus +libcanberra +kf6-kcompletion \
	+kf6-kconfig +kf6-ki18n +kf6-kio
KF6_CMAKE_OPTIONS:=-DUSE_DBUS=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
