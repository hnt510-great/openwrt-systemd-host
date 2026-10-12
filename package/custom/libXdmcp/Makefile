include $(TOPDIR)/rules.mk

PKG_NAME:=libXdmcp
PKG_VERSION:=1.1.5
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=d8a5222828c3adab70adf69a5583f1d32eb5ece04304f7f8392b6a353aa2228c

XORG_DEPENDS:=

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
