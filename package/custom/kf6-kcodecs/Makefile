include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kcodecs
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kcodecs-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=15920b9a859341b13831e6ed49baceea2e728c796fdd082128e51f8e127ff3a0
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Codecs
KF6_DEPENDS:=+qt6base-core

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
