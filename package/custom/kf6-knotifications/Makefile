include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-knotifications
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=knotifications-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=aae6d928eaf52540b642bd9c7ea6293e2c0d0f53612e5fb4f0a6001692f8055a
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Notifications
KF6_DEPENDS:=+qt6base-gui +qt6base-dbus +libcanberra +kf6-kconfig
KF6_CMAKE_OPTIONS:=-DUSE_DBUS=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
