include $(TOPDIR)/rules.mk

PKG_NAME:=libXi
PKG_VERSION:=1.8.4
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=ddd6057b89a91903bc2f884d55c8467440906945e482c36547260dff28661afc

XORG_DEPENDS:=+libX11 +libXext +libXfixes

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
