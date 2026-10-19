include $(TOPDIR)/rules.mk

PKG_NAME:=libXrandr
PKG_VERSION:=1.5.5
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=72b922c2e765434e9e9f0960148070bd4504b288263e2868a4ccce1b7cf2767a

XORG_DEPENDS:=+libX11 +libXext +libXrender

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
