include $(TOPDIR)/rules.mk
PKG_NAME:=at-spi2-core
PKG_VERSION:=2.60.7
PKG_RELEASE:=5
PKG_SOURCE:=at-spi2-core-2.60.7.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/at-spi2-core/2.60/
PKG_HASH:=92893c8188355264ba639ca3d27943437b26ef069971ea9faa4b20de40595b9a
PKG_BUILD_DIR:=$(BUILD_DIR)/at-spi2-core-$(PKG_VERSION)
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host
PKG_CONFIG_DEPENDS:=CONFIG_OPENWRT_SYSTEMD
include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk
include $(INCLUDE_DIR)/gobject-introspection.mk

define Package/at-spi2-core
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=at-spi2-core
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +glib2-gir +libdbus +dbus
endef
MESON_ARGS += -Dintrospection=enabled -Dx11=disabled -Duse_systemd=$(if $(CONFIG_OPENWRT_SYSTEMD),true,false) -Dsystemd_user_dir=/usr/lib/systemd/user -Ddefault_bus=dbus-daemon -Ddbus_daemon=/usr/bin/dbus-daemon -Dgtk2_atk_adaptor=false -Ddocs=false

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/include $(1)/usr/share/gir-1.0 $(1)/usr/lib/girepository-1.0
	[ ! -d $(PKG_INSTALL_DIR)/usr/include ] || $(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/pkgconfig ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/share/gir-1.0 ] || $(CP) $(PKG_INSTALL_DIR)/usr/share/gir-1.0/. $(1)/usr/share/gir-1.0/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0 ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0/. $(1)/usr/lib/girepository-1.0/
endef

define Package/at-spi2-core/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0 ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0 $(1)/usr/lib/
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/usr/share/dbus-1
	$(CP) $(PKG_INSTALL_DIR)/usr/libexec/. $(1)/usr/libexec/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/dbus-1/. $(1)/usr/share/dbus-1/
	$(INSTALL_DIR) $(1)/usr/share/defaults
	$(CP) $(PKG_INSTALL_DIR)/usr/share/defaults/at-spi2 $(1)/usr/share/defaults/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/systemd ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/systemd $(1)/usr/lib/
endef

$(eval $(call BuildPackage,at-spi2-core))
