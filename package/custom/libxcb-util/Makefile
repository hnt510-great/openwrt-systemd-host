include $(TOPDIR)/rules.mk

PKG_NAME:=libxcb-util
PKG_VERSION:=0.4.1
PKG_RELEASE:=1
PKG_SOURCE:=xcb-util-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/xcb/
PKG_HASH:=5abe3bbbd8e54f0fa3ec945291b7e8fa8cfd3cccc43718f8758430f94126e512
PKG_BUILD_DIR:=$(BUILD_DIR)/xcb-util-$(PKG_VERSION)
XORG_DEPENDS:=+libxcb

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
