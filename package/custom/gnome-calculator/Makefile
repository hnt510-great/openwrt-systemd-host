include $(TOPDIR)/rules.mk

PKG_NAME:=gnome-calculator
PKG_VERSION:=51.1
PKG_RELEASE:=1
PKG_SOURCE:=gnome-calculator-51.1.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gnome-calculator/51/
PKG_HASH:=03edf5972adc020b7e872233caba42f759e9879fc4b96f014580f136179c4fa0
PKG_LICENSE:=GPL-3.0-or-later
PKG_LICENSE_FILES:=COPYING
PKG_BUILD_DEPENDS:=vala/host blueprint-compiler/host
GNOME_TITLE:=GNOME Calculator
GNOME_DEPENDS:=+glib2-gir +gtk4 +libadwaita +gtksourceview +libsoup3 +libxml2 +libmpfr +libmpc +libgmp
GNOME_MESON_ARGS:=-Dgcalc=false -Dgci=false -Dapp=true -Ddoc=false -Dui-tests=false -Ddisable-introspection=true -Dlibpath=$(STAGING_DIR)/usr/lib

include $(INCLUDE_DIR)/gnome-package.mk

MESON_VARS += VALAC="$(STAGING_DIR_HOSTPKG)/bin/valac"

define Build/Configure
	$(STAGING_DIR_HOSTPKG)/bin/vapigen \
		--library=libadwaita-1 \
		--pkg=gio-2.0 --pkg=gtk4 \
		--girdir="$(STAGING_DIR)/usr/share/gir-1.0" \
		--vapidir="$(STAGING_DIR)/usr/share/vala/vapi" \
		--directory="$(PKG_BUILD_DIR)/vapi" \
		"$(STAGING_DIR)/usr/share/gir-1.0/Adw-1.gir"
	$(STAGING_DIR_HOSTPKG)/bin/vapigen \
		--library=libsoup-3.0 \
		--pkg=gio-2.0 \
		--girdir="$(STAGING_DIR)/usr/share/gir-1.0" \
		--vapidir="$(STAGING_DIR)/usr/share/vala/vapi" \
		--directory="$(PKG_BUILD_DIR)/vapi" \
		"$(STAGING_DIR)/usr/share/gir-1.0/Soup-3.0.gir"
	[ ! -d "$(STAGING_DIR)/usr/share/vala/vapi" ] || $(CP) "$(STAGING_DIR)/usr/share/vala/vapi/"* "$(PKG_BUILD_DIR)/vapi/"
	$(call Build/Configure/Meson)
endef

$(eval $(call BuildPackage,$(PKG_NAME)))
