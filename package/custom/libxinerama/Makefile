include $(TOPDIR)/rules.mk

PKG_NAME:=libXinerama
PKG_VERSION:=1.1.6
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=d00fc1599c303dc5cbc122b8068bdc7405d6fcb19060f4597fc51bd3a8be51d7
XORG_DEPENDS:=+libX11 +libXext

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
