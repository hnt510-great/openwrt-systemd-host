include $(TOPDIR)/rules.mk

PKG_NAME:=libkscreen
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=8f0e2157bb55aa36ac632c85bd4411bcbf2424c477cca3126b8b42ad33fa4fb8
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=libkscreen
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-dbus +qt6waylandclient +libwayland
PKG_BUILD_DEPENDS:=wayland wayland-protocols plasma-wayland-protocols

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
