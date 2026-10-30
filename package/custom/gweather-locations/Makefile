include $(TOPDIR)/rules.mk

PKG_NAME:=gweather-locations
PKG_VERSION:=2026.2
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gweather-locations/2026/
PKG_HASH:=e7570a3661e0a752a06387b2032585cf588fc56770b1f9f39f1a55d17b2835fe
PKG_LICENSE:=GPL-2.0-or-later
PKG_LICENSE_FILES:=COPYING
PKG_INSTALL:=1
PKG_BUILD_DEPENDS:=pygobject/host glib2-gir

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

MESON_USE_STAGING_PYTHON:=1
MESON_ARGS += --prefix=/usr --libdir=lib
# Run the native generator with host PyGObject and the staged GLib typelib.
MESON_VARS += GI_TYPELIB_PATH="$(STAGING_DIR)/usr/lib/girepository-1.0" \
	LD_LIBRARY_PATH="$(STAGING_DIR_HOSTPKG)/lib"

define Package/gweather-locations
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=Location database for libgweather
  URL:=https://gitlab.gnome.org/GNOME/gweather-locations
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC
endef

define Build/Configure
	# The upstream generator serializes GVariant data in native endianness.
	$(STAGING_DIR_HOSTPKG)/bin/python3 -c 'import sys; assert sys.byteorder == "little", "x86 location data requires a little-endian build host"'
	$(call Build/Configure/Meson)
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/share/pkgconfig
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/pkgconfig/gweather-locations.pc $(1)/usr/share/pkgconfig/
endef

define Package/gweather-locations/install
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/share
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/gweather-locations $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/gweather-locations $(1)/usr/share/
	[ ! -d $(PKG_INSTALL_DIR)/usr/share/locale ] || $(CP) $(PKG_INSTALL_DIR)/usr/share/locale $(1)/usr/share/
endef

$(eval $(call BuildPackage,gweather-locations))
