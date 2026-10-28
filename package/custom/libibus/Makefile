include $(TOPDIR)/rules.mk

PKG_NAME:=libibus
PKG_VERSION:=1.5.34
PKG_RELEASE:=1
PKG_SOURCE:=ibus-1.5.34.tar.gz
PKG_SOURCE_URL:=https://github.com/ibus/ibus/releases/download/1.5.34/
PKG_HASH:=12a72210ce5250f8a66df562a75e034e67b2bce74c4df2983dc86d1154894943
PKG_BUILD_DIR:=$(BUILD_DIR)/ibus-$(PKG_VERSION)
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_FIXUP:=autoreconf
PKG_FILE_DEPENDS:=$(TOPDIR)/scripts/gnome-host-pkg-config
PKG_BUILD_PARALLEL:=1
MAKE_PATH:=src
PKG_BUILD_DEPENDS:=glib2/host gobject-introspection/host gobject-introspection python3/host

include $(INCLUDE_DIR)/package.mk

define Package/libibus
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=IBus client API and GNOME introspection
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +glib2-gir +dbus
endef

CONFIGURE_ARGS += --disable-gtk2 --disable-gtk3 --disable-gtk4 --disable-ui --disable-appindicator \
	--disable-engine --disable-setup --disable-python-library --disable-python2 \
	--disable-xim --disable-wayland --disable-tests --disable-install-tests \
	--disable-emoji-dict --disable-unicode-dict --disable-dconf --disable-gtk-doc \
	--disable-systemd-services --disable-vala --disable-libnotify --enable-introspection
CONFIGURE_VARS += X11_LOCALEDATADIR=/usr/share/X11/locale \
	PKG_CONFIG_FOR_BUILD="$(TOPDIR)/scripts/gnome-host-pkg-config" \
	CC_FOR_BUILD="$(HOSTCC_NOCACHE)" CFLAGS_FOR_BUILD="$(HOST_CFLAGS)" LDFLAGS_FOR_BUILD="$(HOST_LDFLAGS)" \
	GI_CROSS_LAUNCHER="$(TOPDIR)/scripts/gi-target-runner" \
	GI_SCANNER="$(STAGING_DIR)/usr/bin/g-ir-scanner" GI_COMPILER="$(STAGING_DIR)/usr/bin/g-ir-compiler"

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig $(1)/usr/lib/girepository-1.0 $(1)/usr/share/gir-1.0
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/ibus-1.0.pc $(1)/usr/lib/pkgconfig/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0/*.typelib $(1)/usr/lib/girepository-1.0/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/gir-1.0/*.gir $(1)/usr/share/gir-1.0/
endef

define Package/libibus/install
	$(INSTALL_DIR) $(1)/usr/lib/girepository-1.0
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libibus-1.0.so.* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0/*.typelib $(1)/usr/lib/girepository-1.0/
endef

$(eval $(call BuildPackage,libibus))
