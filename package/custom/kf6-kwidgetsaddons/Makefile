include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kwidgetsaddons
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kwidgetsaddons-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=39974b85cdffd8c6d6e0a5c0684927a21e071c1e63d7cce3888331f0169a4837
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Widgets Addons
KF6_DEPENDS:=+qt6base-widgets

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
