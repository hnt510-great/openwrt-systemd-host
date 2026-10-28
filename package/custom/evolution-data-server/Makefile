include $(TOPDIR)/rules.mk

PKG_NAME:=evolution-data-server
PKG_VERSION:=3.60.2
PKG_RELEASE:=1
PKG_SOURCE:=evolution-data-server-3.60.2.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/evolution-data-server/3.60/
PKG_HASH:=2084dbdac396371b365d504c1ff45866ba8dca2f1252e5da1d3d9c33abdc1286
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host gobject-introspection/host gobject-introspection

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

define Package/evolution-data-server
  SECTION:=utils
  CATEGORY:=Utilities
  SUBMENU:=GNOME desktop
  TITLE:=GNOME calendar and address-book data services
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +glibc-gconv +glib2-gir +libical-glib +libsoup3 +libsecret +libxml2 +libsqlite3 +libuuid +libnss +nspr +icu +json-glib +zlib
endef

CMAKE_OPTIONS += -DLIB_SUFFIX= -DENABLE_TESTS=OFF -DENABLE_INSTALLED_TESTS=OFF \
	-DCMAKE_SKIP_RPATH=OFF -DCMAKE_INSTALL_RPATH_USE_LINK_PATH=OFF \
	-DENABLE_EXAMPLES=OFF -DENABLE_GTK=OFF -DENABLE_GTK4=OFF \
	-DENABLE_GOA=OFF -DENABLE_WEATHER=OFF -DENABLE_CANBERRA=OFF \
	-DENABLE_INTROSPECTION=ON -DENABLE_VALA_BINDINGS=OFF -DENABLE_GTK_DOC=OFF \
	-DWITH_KRB5=OFF -DWITH_OPENLDAP=OFF -DWITH_LIBDB=OFF \
	-DWITH_SYSTEMDUSERUNITDIR=/usr/lib/systemd/user \
	-DCMAKE_CROSSCOMPILING_EMULATOR=$(TOPDIR)/scripts/gi-target-runner
MAKE_FLAGS += GI_CROSS_LAUNCHER="$(TOPDIR)/scripts/gi-target-runner"

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib $(1)/usr/share/gir-1.0
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/. $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/gir-1.0/. $(1)/usr/share/gir-1.0/
	for pc in $(1)/usr/lib/pkgconfig/*.pc; do \
		$(SED) 's|=/usr/|=$$$${prefix}/|g;s|^Libs:.*|& -Wl,-rpath-link,$$$${libdir}/evolution-data-server|' $$$$pc; \
	done
endef

define Package/evolution-data-server/install
	$(CP) $(PKG_INSTALL_DIR)/usr $(1)/
	[ ! -d $(PKG_INSTALL_DIR)/etc ] || $(CP) $(PKG_INSTALL_DIR)/etc $(1)/
	$(RM) -r $(1)/usr/include $(1)/usr/lib/pkgconfig $(1)/usr/lib/cmake $(1)/usr/share/gir-1.0 $(1)/usr/share/gtk-doc
endef

$(eval $(call BuildPackage,evolution-data-server))
