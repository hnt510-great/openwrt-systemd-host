include $(TOPDIR)/rules.mk

PKG_NAME:=baobab
PKG_VERSION:=50.0
PKG_RELEASE:=1
PKG_SOURCE:=baobab-50.0.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/baobab/50/
PKG_HASH:=573c84f15f5f963a440500f6f43412c928ac2335f6b69dcb58f1a1fe5201024b
PKG_LICENSE:=GPL-2.0-or-later
PKG_LICENSE_FILES:=COPYING
PKG_BUILD_DEPENDS:=vala/host
GNOME_TITLE:=GNOME Disk Usage Analyzer
GNOME_DEPENDS:=+glib2 +gtk4 +libadwaita
GNOME_MESON_ARGS:=

include $(INCLUDE_DIR)/gnome-package.mk

MESON_VARS += VALAC="$(STAGING_DIR_HOSTPKG)/bin/valac"

define Build/Configure
	$(STAGING_DIR_HOSTPKG)/bin/vapigen \
		--library=libadwaita-1 \
		--pkg=gio-2.0 --pkg=gtk4 \
		--girdir="$(STAGING_DIR)/usr/share/gir-1.0" \
		--vapidir="$(STAGING_DIR)/usr/share/vala/vapi" \
		--directory="$(PKG_BUILD_DIR)/src" \
		"$(STAGING_DIR)/usr/share/gir-1.0/Adw-1.gir"
	$(call Build/Configure/Meson)
endef

$(eval $(call BuildPackage,$(PKG_NAME)))
