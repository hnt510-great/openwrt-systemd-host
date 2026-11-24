include $(TOPDIR)/rules.mk

PKG_NAME:=kdecoration
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=77435cc9dda43ff14e6b99cfb08498ace7730f995fc4ab4c21d6be2d1a6c73a1
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=KDecoration3
KF6_DEPENDS:=+qt6base-core +qt6base-gui +kf6-ki18n

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
