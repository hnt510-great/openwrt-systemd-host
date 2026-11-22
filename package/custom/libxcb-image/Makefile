include $(TOPDIR)/rules.mk

PKG_NAME:=libxcb-image
PKG_VERSION:=0.4.1
PKG_RELEASE:=1
PKG_SOURCE:=xcb-util-image-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/xcb/
PKG_HASH:=ccad8ee5dadb1271fd4727ad14d9bd77a64e505608766c4e98267d9aede40d3d
PKG_BUILD_DIR:=$(BUILD_DIR)/xcb-util-image-$(PKG_VERSION)
XORG_DEPENDS:=+libxcb +libxcb-util

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
