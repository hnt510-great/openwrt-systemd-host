include $(TOPDIR)/rules.mk

PKG_NAME:=libgdm
PKG_VERSION:=51.1.1
PKG_RELEASE:=2
PKG_SOURCE:=gdm-51.1.1.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gdm/51/
PKG_HASH:=390ae9e7540f71db28a3dc64319a8f687f4d88bd4d5f1ff816b7a9f2249ab4aa
PKG_BUILD_DIR:=$(BUILD_DIR)/gdm-$(PKG_VERSION)
PKG_LICENSE:=LGPL-2.1-or-later
GNOME_TITLE:=GDM client library and introspection for GNOME Shell
GNOME_DEPENDS:=+glib2-gir +libsystemd +libpam +libgudev +json-glib +accountsservice +polkit
GNOME_MESON_ARGS:=-Dx11-support=false -Dplymouth=disabled -Dselinux=disabled -Dlibaudit=disabled -Ddefault-pam-config=none

include $(INCLUDE_DIR)/gnome-package.mk

define Build/Install
	$(call Build/Install/Meson)
	$(INSTALL_DIR) $(PKG_INSTALL_DIR)/usr/share/glib-2.0/schemas
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/data/org.gnome.login-screen.gschema.xml \
		$(PKG_INSTALL_DIR)/usr/share/glib-2.0/schemas/
endef

$(eval $(call BuildPackage,$(PKG_NAME)))
