include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kstatusnotifieritem
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kstatusnotifieritem-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=46c9ebf7d5319a2bde9123427edb277b871740f4f79f65e79a382dde7e1891d9
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=KStatusNotifierItem
KF6_DEPENDS:=+qt6base-gui +qt6base-widgets +qt6base-dbus +kf6-kwindowsystem

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
