include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kitemviews
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kitemviews-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=63f6d64780d3eb1bfdd2f2f9036026a2cdc163b676168c29c2797544f9ad6305
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Item Views
KF6_DEPENDS:=+qt6base-widgets

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
