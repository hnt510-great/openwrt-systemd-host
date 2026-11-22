include $(TOPDIR)/rules.mk

PKG_NAME:=libxcb-cursor
PKG_VERSION:=0.1.6
PKG_RELEASE:=1
PKG_SOURCE:=xcb-util-cursor-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/xcb/
PKG_HASH:=fdeb8bd127873519be5cc70dcd0d3b5d33b667877200f9925a59fdcad8f7a933
PKG_BUILD_DIR:=$(BUILD_DIR)/xcb-util-cursor-$(PKG_VERSION)
XORG_DEPENDS:=+libxcb +libxcb-image +libxcb-render-util +libxcb-util

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
