include $(TOPDIR)/rules.mk

PKG_NAME:=libXxf86vm
PKG_VERSION:=1.1.7
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=ae50c0f669e0af5a67cc4cd0f54f21d64a64d2660af883e80e95d3fe51b945d8

XORG_DEPENDS:=+libX11 +libXext

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
