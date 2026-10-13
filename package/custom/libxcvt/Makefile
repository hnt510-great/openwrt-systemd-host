include $(TOPDIR)/rules.mk

PKG_NAME:=libxcvt
PKG_VERSION:=0.1.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=a929998a8767de7dfa36d6da4751cdbeef34ed630714f2f4a767b351f2442e01

XORG_DEPENDS:=

include ../xorg-meson.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
