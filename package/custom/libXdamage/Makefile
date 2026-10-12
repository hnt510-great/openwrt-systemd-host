include $(TOPDIR)/rules.mk

PKG_NAME:=libXdamage
PKG_VERSION:=1.1.6
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=52733c1f5262fca35f64e7d5060c6fcd81a880ba8e1e65c9621cf0727afb5d11

XORG_DEPENDS:=+libX11 +libXfixes

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
