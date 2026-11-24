include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kcoreaddons
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kcoreaddons-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=f7373a77afae97099de4359fba13987b46618ccb952f94ddc11c9d31277fe651
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Core Addons
KF6_DEPENDS:=+qt6base-core +qt6base-dbus +qt6base-network +qt6quick-qml +libudev
KF6_CMAKE_OPTIONS:=-DKCOREADDONS_USE_QML=ON -DUSE_DBUS=ON -DENABLE_INOTIFY=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
