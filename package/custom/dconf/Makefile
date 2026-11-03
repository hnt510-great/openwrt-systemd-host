include $(TOPDIR)/rules.mk
PKG_NAME:=dconf
PKG_VERSION:=0.40.0
PKG_RELEASE:=2
PKG_SOURCE:=dconf-0.40.0.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/dconf/0.40/
PKG_HASH:=cf7f22a4c9200421d8d3325c5c1b8b93a36843650c9f95d6451e20f0bcb24533
PKG_BUILD_DIR:=$(BUILD_DIR)/dconf-$(PKG_VERSION)
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host
include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/dconf
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=dconf
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +glib2 +dbus
endef
MESON_ARGS += -Dvapi=false -Dman=false -Dgtk_doc=false -Dbash_completion=false \
	-Dsystemduserunitdir=/usr/lib/systemd/user

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/include $(1)/usr/share/gir-1.0 $(1)/usr/lib/girepository-1.0
	[ ! -d $(PKG_INSTALL_DIR)/usr/include ] || $(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/pkgconfig ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/share/gir-1.0 ] || $(CP) $(PKG_INSTALL_DIR)/usr/share/gir-1.0/. $(1)/usr/share/gir-1.0/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0 ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0/. $(1)/usr/lib/girepository-1.0/
endef

define Package/dconf/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0 ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0 $(1)/usr/lib/
	$(INSTALL_DIR) $(1)/usr/lib/gio/modules $(1)/usr/libexec $(1)/usr/share/dbus-1
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/gio/modules/*.so $(1)/usr/lib/gio/modules/
	$(CP) $(PKG_INSTALL_DIR)/usr/libexec/. $(1)/usr/libexec/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/dbus-1/. $(1)/usr/share/dbus-1/
	$(INSTALL_DIR) $(1)/usr/lib/systemd/user
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/systemd/user/dconf.service $(1)/usr/lib/systemd/user/
endef

$(eval $(call BuildPackage,dconf))
