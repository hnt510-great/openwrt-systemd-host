include $(TOPDIR)/rules.mk

PKG_NAME:=milou
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=87706400f9f82277cba4aeffbcc8d67e74b89f33038a7d49c0e7db6db3138f86
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=Milou search
KF6_DEPENDS:=+qt6quick +qt6base-widgets +kf6-ki18n +kf6-krunner +kf6-ksvg +kf6-kconfig +libplasma

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
