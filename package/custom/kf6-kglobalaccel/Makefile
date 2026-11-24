include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kglobalaccel
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kglobalaccel-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=d5ad10eb041ef8f46074bb1df4cf3475888421d849bc667a7afc6c5bf8cc1640
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Global Accel
KF6_DEPENDS:=+qt6base-dbus +qt6base-gui +qt6base-widgets +kf6-kconfig \
	+kf6-kcoreaddons +kf6-kdbusaddons +kf6-kwindowsystem

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
