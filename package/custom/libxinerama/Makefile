include $(TOPDIR)/rules.mk

PKG_NAME:=libXinerama
PKG_VERSION:=1.1.5
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=5094d1f0fcc1828cb1696d0d39d9e866ae32520c54d01f618f1a3c1e30c2085c
XORG_DEPENDS:=+libX11 +libXext

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
