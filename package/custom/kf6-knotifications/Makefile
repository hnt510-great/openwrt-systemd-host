include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-knotifications
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=knotifications-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=5da86674bfbe532427f2ea52c86e6d5220cdfb8d0fadb8cbec2ba53d48ec5be9
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Notifications
KF6_DEPENDS:=+qt6base-gui +qt6base-dbus +qt6quick-qml +libcanberra +kf6-kconfig
KF6_CMAKE_OPTIONS:=-DUSE_DBUS=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
