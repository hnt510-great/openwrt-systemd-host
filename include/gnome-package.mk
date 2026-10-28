# Shared native GNOME staging. Recipes declare their own source, dependencies
# and Meson options; all generators run with the staged host Python/tools.
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS+=glib2/host
PKG_FILE_DEPENDS+=$(INCLUDE_DIR)/gnome-package.mk
MESON_USE_STAGING_PYTHON:=1

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk
include $(INCLUDE_DIR)/gobject-introspection.mk

MESON_VARS += GI_TYPELIB_PATH="$(STAGING_DIR)/usr/lib/girepository-1.0" \
	XDG_DATA_DIRS="$(STAGING_DIR)/usr/share:$(STAGING_DIR_HOSTPKG)/share:/usr/share"

define Package/$(PKG_NAME)
  SECTION:=utils
  CATEGORY:=Utilities
  SUBMENU:=GNOME desktop
  TITLE:=$(GNOME_TITLE)
  URL:=https://www.gnome.org/
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD $(GNOME_DEPENDS)
endef

MESON_ARGS += --prefix=/usr --libdir=lib --libexecdir=libexec \
	--sysconfdir=/etc --localstatedir=/var --wrap-mode=nodownload $(GNOME_MESON_ARGS)

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib $(1)/usr/share
	[ ! -d $(PKG_INSTALL_DIR)/usr/include ] || $(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/. $(1)/usr/lib/
	for dir in pkgconfig gir-1.0 glib-2.0; do \
		[ ! -d $(PKG_INSTALL_DIR)/usr/share/$$$$dir ] || $(CP) $(PKG_INSTALL_DIR)/usr/share/$$$$dir $(1)/usr/share/; \
	done
endef

define Package/$(PKG_NAME)/install
	[ ! -d $(PKG_INSTALL_DIR)/usr ] || $(CP) $(PKG_INSTALL_DIR)/usr $(1)/
	[ ! -d $(PKG_INSTALL_DIR)/etc ] || $(CP) $(PKG_INSTALL_DIR)/etc $(1)/
	$(RM) -r $(1)/usr/include $(1)/usr/lib/pkgconfig $(1)/usr/share/pkgconfig \
		$(1)/usr/share/gir-1.0 $(1)/usr/share/gtk-doc $(1)/usr/share/doc $(1)/usr/share/man
	find $(1) -type f \( -name '*.a' -o -name '*.la' \) -delete
endef

define Package/$(PKG_NAME)/postinst
#!/bin/sh
[ -n "$$IPKG_INSTROOT" ] || /usr/libexec/glib2-cache-update
exit 0
endef
