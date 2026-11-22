include $(TOPDIR)/rules.mk

PKG_NAME:=libxcb-cursor
PKG_VERSION:=0.1.5
PKG_RELEASE:=1
PKG_SOURCE:=xcb-util-cursor-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/xcb/
PKG_HASH:=0caf99b0d60970f81ce41c7ba694e5eaaf833227bb2cbcdb2f6dc9666a663c57
PKG_BUILD_DIR:=$(BUILD_DIR)/xcb-util-cursor-$(PKG_VERSION)
XORG_DEPENDS:=+libxcb +libxcb-image +libxcb-render-util +libxcb-util

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
