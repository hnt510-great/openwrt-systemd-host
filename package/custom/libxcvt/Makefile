include $(TOPDIR)/rules.mk

PKG_NAME:=libxcvt
PKG_VERSION:=0.1.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=a929998a8767de7dfa36d6da4751cdbeef34ed630714f2f4a767b351f2442e01

XORG_DEPENDS:=

include $(INCLUDE_DIR)/host-build.mk
include ../xorg-meson.mk

# mutter runs the cvt tool at build time to generate its default mode table.
# libxcvt is always shared, so point cvt at the staged library.
HOST_LDFLAGS += -Wl,-rpath,$(STAGING_DIR_HOSTPKG)/lib

$(eval $(call HostBuild))
$(eval $(call BuildPackage,$(PKG_NAME)))
