include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-attica
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=attica-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=4f2b525649c6a23924bdf2647e9cd6c591285d33d8d4f01db45b37622e3b839b
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Attica
KF6_DEPENDS:=+qt6base-core +qt6base-network

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
