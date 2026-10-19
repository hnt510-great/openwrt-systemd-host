include $(TOPDIR)/rules.mk

PKG_NAME:=libXrender
PKG_VERSION:=0.9.13
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=3fe88c609df6782e1e7af2e4de36b2563d70cd70ff7dcb1cda561ad64912bb64

XORG_DEPENDS:=+libX11

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
