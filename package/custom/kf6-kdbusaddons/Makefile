include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kdbusaddons
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kdbusaddons-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=84dd9e0775ccff18eb751f6a86ea909bf9eb4a95596baef097684b6646e33764
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=DBus Addons
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-dbus

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
