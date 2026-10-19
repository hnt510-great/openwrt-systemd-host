include $(TOPDIR)/rules.mk

PKG_NAME:=libXext
PKG_VERSION:=1.3.7
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=6c643c7035cdacf67afd68f25d01b90ef889d546c9fcd7c0adf7c2cf91e3a32d

XORG_DEPENDS:=+libX11

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
