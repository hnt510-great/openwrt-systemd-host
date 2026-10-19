include $(TOPDIR)/rules.mk

PKG_NAME:=libXdamage
PKG_VERSION:=1.1.7
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=127067f521d3ee467b97bcb145aeba1078e2454d448e8748eb984d5b397bde24

XORG_DEPENDS:=+libX11 +libXfixes

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
