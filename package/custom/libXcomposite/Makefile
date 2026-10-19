include $(TOPDIR)/rules.mk

PKG_NAME:=libXcomposite
PKG_VERSION:=0.4.7
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=8bdf310967f484503fa51714cf97bff0723d9b673e0eecbf92b3f97c060c8ccb

XORG_DEPENDS:=+libX11 +libXext +libXfixes

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
