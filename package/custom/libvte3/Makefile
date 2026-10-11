include $(TOPDIR)/rules.mk
PKG_NAME:=libvte3
PKG_VERSION:=0.82.3
PKG_RELEASE:=1
PKG_SOURCE:=vte-0.82.3.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/vte/0.82/
PKG_HASH:=6dc6278f6fee30d07d1a03e2ba3335b1ea4e8d2956ceb59d861943115d930a85
PKG_BUILD_DIR:=$(BUILD_DIR)/vte-$(PKG_VERSION)
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host
include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk
include $(INCLUDE_DIR)/gobject-introspection.mk

define Package/libvte3
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=libvte3
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +libgtk3 +libpcre2 +liblz4 +libgnutls +icu +fribidi +zlib +libstdcpp
endef
MESON_ARGS += -Dgtk3=true -Dgtk4=false -Dgir=true -Dvapi=false -Ddocs=false -Dapp=false -Dglade=false -D_systemd=false

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/include $(1)/usr/share/gir-1.0 $(1)/usr/lib/girepository-1.0
	[ ! -d $(PKG_INSTALL_DIR)/usr/include ] || $(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/pkgconfig ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/share/gir-1.0 ] || $(CP) $(PKG_INSTALL_DIR)/usr/share/gir-1.0/. $(1)/usr/share/gir-1.0/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0 ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0/. $(1)/usr/lib/girepository-1.0/
endef

define Package/libvte3/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0 ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0 $(1)/usr/lib/

endef

$(eval $(call BuildPackage,libvte3))
