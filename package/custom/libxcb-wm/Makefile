include $(TOPDIR)/rules.mk

PKG_NAME:=libxcb-wm
PKG_VERSION:=0.4.2
PKG_RELEASE:=1
PKG_SOURCE:=xcb-util-wm-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/xcb/
PKG_HASH:=62c34e21d06264687faea7edbf63632c9f04d55e72114aa4a57bb95e4f888a0b
PKG_BUILD_DIR:=$(BUILD_DIR)/xcb-util-wm-$(PKG_VERSION)
XORG_DEPENDS:=+libxcb

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
