include $(TOPDIR)/rules.mk
PKG_NAME:=gtk-vnc
PKG_VERSION:=1.5.0
PKG_RELEASE:=1
PKG_SOURCE:=gtk-vnc-1.5.0.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gtk-vnc/1.5/
PKG_HASH:=c0beb4747528ad931da43acc567c6a0190f7fc624465571ed9ccece02c34dd23
PKG_BUILD_DIR:=$(BUILD_DIR)/gtk-vnc-$(PKG_VERSION)
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host
include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk
include $(INCLUDE_DIR)/gobject-introspection.mk

define Package/gtk-vnc
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=gtk-vnc
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +libgtk3 +libgnutls +libgcrypt +libjpeg +zlib
endef
MESON_ARGS += -Dintrospection=enabled -Dpulseaudio=disabled -Dsasl=disabled -Dwith-vala=disabled -Dgi-docs=disabled

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/include $(1)/usr/share/gir-1.0 $(1)/usr/lib/girepository-1.0
	[ ! -d $(PKG_INSTALL_DIR)/usr/include ] || $(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/pkgconfig ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/share/gir-1.0 ] || $(CP) $(PKG_INSTALL_DIR)/usr/share/gir-1.0/. $(1)/usr/share/gir-1.0/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0 ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0/. $(1)/usr/lib/girepository-1.0/
endef

define Package/gtk-vnc/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0 ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0 $(1)/usr/lib/

endef

$(eval $(call BuildPackage,gtk-vnc))
