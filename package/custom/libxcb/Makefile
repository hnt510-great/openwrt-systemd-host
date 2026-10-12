include $(TOPDIR)/rules.mk

PKG_NAME:=libxcb
PKG_VERSION:=1.17.0
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xcb.freedesktop.org/dist/
PKG_HASH:=599ebf9996710fea71622e6e184f3a8ad5b43d0e5fa8c4e407123c88a59a6d55

XORG_DEPENDS:=+libXau +libXdmcp
PKG_BUILD_DEPENDS:=xcb-proto xcb-proto/host python3/host

include ../xorg-client.mk

# XML descriptions are target-independent; only the generator runs on the host.
CONFIGURE_VARS += PYTHON="$(STAGING_DIR_HOSTPKG)/bin/python3"
CONFIGURE_ARGS += --enable-xinput --enable-xkb --without-doxygen
MAKE_FLAGS += XCBPROTO_XCBINCLUDEDIR="$(STAGING_DIR)/usr/share/xcb" XCBPROTO_XCBPYTHONDIR="$(STAGING_DIR_HOSTPKG)/lib/xcb-proto"

$(eval $(call BuildPackage,$(PKG_NAME)))
