include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kcodecs
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kcodecs-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=2fc1ab6900df8488fe69811fde58ab37c7c6fdf6c1f1b32a01c20f3b3d9f6d9c
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Codecs
KF6_DEPENDS:=+qt6base-core

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
