include $(TOPDIR)/rules.mk

PKG_NAME:=libXau
PKG_VERSION:=1.0.12
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=74d0e4dfa3d39ad8939e99bda37f5967aba528211076828464d2777d477fc0fb

XORG_DEPENDS:=

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
