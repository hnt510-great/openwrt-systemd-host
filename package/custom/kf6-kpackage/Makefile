include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kpackage
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kpackage-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=61884114af604f827c4b83634551ea64921050e233c9c6d5fc400b97e402529e
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Package
KF6_DEPENDS:=+qt6base-core +qt6base-dbus +kf6-karchive +kf6-kcoreaddons +kf6-ki18n
KF6_CMAKE_OPTIONS:=-DUSE_DBUS=ON -DCMAKE_DISABLE_FIND_PACKAGE_KF6DocTools=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
