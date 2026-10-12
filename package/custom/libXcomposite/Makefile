include $(TOPDIR)/rules.mk

PKG_NAME:=libXcomposite
PKG_VERSION:=0.4.6
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=fe40bcf0ae1a09070eba24088a5eb9810efe57453779ec1e20a55080c6dc2c87

XORG_DEPENDS:=+libX11 +libXext +libXfixes

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
