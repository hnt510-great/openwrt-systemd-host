include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-attica
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=attica-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=8ef95ad2798763202cdd659521bbe64ca58ec8ca68465eace4a817a2ff2e4dc4
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Attica
KF6_DEPENDS:=+qt6base-core +qt6base-network

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
