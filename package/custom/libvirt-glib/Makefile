include $(TOPDIR)/rules.mk
PKG_NAME:=libvirt-glib
PKG_VERSION:=5.0.0
PKG_RELEASE:=1
PKG_SOURCE:=libvirt-glib-5.0.0.tar.xz
PKG_SOURCE_URL:=https://libvirt.org/sources/glib/
PKG_HASH:=9bfec346382416a3575d87299bc641b2a464aa519fd9b1287e318aa43a2f3b8b
PKG_BUILD_DIR:=$(BUILD_DIR)/libvirt-glib-$(PKG_VERSION)
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host
include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk
include $(INCLUDE_DIR)/gobject-introspection.mk

define Package/libvirt-glib
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=libvirt-glib
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +glib2-gir +libvirt
endef
MESON_ARGS += -Dintrospection=enabled -Dvapi=disabled -Ddocs=disabled -Dtests=disabled -Dgit_werror=disabled

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/include $(1)/usr/share/gir-1.0 $(1)/usr/lib/girepository-1.0
	[ ! -d $(PKG_INSTALL_DIR)/usr/include ] || $(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/pkgconfig ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/gir-1.0/. $(1)/usr/share/gir-1.0/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0/. $(1)/usr/lib/girepository-1.0/
endef

define Package/libvirt-glib/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0 $(1)/usr/lib/

endef

$(eval $(call BuildPackage,libvirt-glib))
