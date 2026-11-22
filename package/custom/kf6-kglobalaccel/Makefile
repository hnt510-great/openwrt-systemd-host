include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kglobalaccel
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kglobalaccel-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=ee2abd91df47a6ae478f86e67f463487e30032f3c0d8cfd77f2d6b9567c86db4
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Global Accel
KF6_DEPENDS:=+qt6base-dbus +qt6base-gui +qt6base-widgets +kf6-kconfig \
	+kf6-kcoreaddons +kf6-kdbusaddons +kf6-kwindowsystem

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
