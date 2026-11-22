include $(TOPDIR)/rules.mk

PKG_NAME:=libxcb-keysyms
PKG_VERSION:=0.4.1
PKG_RELEASE:=1
PKG_SOURCE:=xcb-util-keysyms-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/xcb/
PKG_HASH:=7c260a5294412aed429df1da2f8afd3bd07b7cba3fec772fba15a613a6d5c638
PKG_BUILD_DIR:=$(BUILD_DIR)/xcb-util-keysyms-$(PKG_VERSION)
XORG_DEPENDS:=+libxcb

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
