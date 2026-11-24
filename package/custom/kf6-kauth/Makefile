include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kauth
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kauth-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=5bcdb298a2ee84bca93a989247fd6d6e34a1e1029caae17705a85b8ac4dbe837
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=KAuth
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-dbus +kf6-kcoreaddons +kf6-kwindowsystem +polkit-qt6
PKG_BUILD_DEPENDS:=polkit-qt6
KF6_CMAKE_OPTIONS:=-DKAUTH_BACKEND_NAME=POLKITQT6-1

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
