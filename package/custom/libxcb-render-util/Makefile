include $(TOPDIR)/rules.mk

PKG_NAME:=libxcb-render-util
PKG_VERSION:=0.3.10
PKG_RELEASE:=1
PKG_SOURCE:=xcb-util-renderutil-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/xcb/
PKG_HASH:=3e15d4f0e22d8ddbfbb9f5d77db43eacd7a304029bf25a6166cc63caa96d04ba
PKG_BUILD_DIR:=$(BUILD_DIR)/xcb-util-renderutil-$(PKG_VERSION)
XORG_DEPENDS:=+libxcb

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
