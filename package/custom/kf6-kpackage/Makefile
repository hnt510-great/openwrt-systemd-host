include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kpackage
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kpackage-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=f3959f4a5956a29ce9bd083410d7df63d4f93a1a4e451cb87c2ccf834995e3ca
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Package
KF6_DEPENDS:=+qt6base-core +qt6base-dbus +kf6-karchive +kf6-kcoreaddons +kf6-ki18n
KF6_CMAKE_OPTIONS:=-DUSE_DBUS=ON -DCMAKE_DISABLE_FIND_PACKAGE_KF6DocTools=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
