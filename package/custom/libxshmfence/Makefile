include $(TOPDIR)/rules.mk

PKG_NAME:=libxshmfence
PKG_VERSION:=1.3.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=d4a4df096aba96fea02c029ee3a44e11a47eb7f7213c1a729be83e85ec3fde10

XORG_DEPENDS:=

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
