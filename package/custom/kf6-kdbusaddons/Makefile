include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kdbusaddons
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kdbusaddons-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=5db2f6b7235238070224ee8a5225f41ffdb3249d558a81a7c06a8e54d67729f7
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=DBus Addons
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-dbus

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
