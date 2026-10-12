include $(TOPDIR)/rules.mk

PKG_NAME:=libXrandr
PKG_VERSION:=1.5.4
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=1ad5b065375f4a85915aa60611cc6407c060492a214d7f9daf214be752c3b4d3

XORG_DEPENDS:=+libX11 +libXext +libXrender

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
