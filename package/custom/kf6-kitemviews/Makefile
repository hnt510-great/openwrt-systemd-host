include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kitemviews
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kitemviews-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=fcd869d9e7cea6e296ae0240a6fab07f31762afcc3f427381db703f9fddaef28
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Item Views
KF6_DEPENDS:=+qt6base-widgets

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
