include $(TOPDIR)/rules.mk

PKG_NAME:=libXext
PKG_VERSION:=1.3.6
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=edb59fa23994e405fdc5b400afdf5820ae6160b94f35e3dc3da4457a16e89753

XORG_DEPENDS:=+libX11

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
