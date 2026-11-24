include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-knotifyconfig
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=knotifyconfig-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=708e19857b4ac7ccf82541319d2a3bac30c1b451e79e4b0c71e6f58bc1b5307a
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Notify Config
KF6_DEPENDS:=+qt6base-widgets +qt6base-dbus +libcanberra +kf6-kcompletion \
	+kf6-kconfig +kf6-ki18n +kf6-kio
KF6_CMAKE_OPTIONS:=-DUSE_DBUS=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
