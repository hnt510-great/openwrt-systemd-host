include $(TOPDIR)/rules.mk

PKG_NAME:=libgdm
PKG_VERSION:=51.2
PKG_RELEASE:=1
PKG_SOURCE:=gdm-51.2.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gdm/51/
PKG_HASH:=b9e5f940ba8a4a2a488f84f756c1be5b79c520931e054e82db4fe91d37feb03d
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
