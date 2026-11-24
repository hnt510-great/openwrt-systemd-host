include $(TOPDIR)/rules.mk

PKG_NAME:=adwaita-icons
PKG_VERSION:=51.0
PKG_RELEASE:=1

PKG_SOURCE:=adwaita-icon-theme-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/adwaita-icon-theme/51/
PKG_HASH:=ba561cf3c96305a47179fa5605856ad695c9238ea07f7093aebd9ba80c4e323b
PKG_BUILD_DIR:=$(BUILD_DIR)/adwaita-icon-theme-$(PKG_VERSION)

PKG_LICENSE:=CC-BY-SA-3.0 LGPL-3.0-or-later
PKG_INSTALL:=1
MESON_USE_STAGING_PYTHON:=1

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/adwaita-icons
  SECTION:=utils
  CATEGORY:=Utilities
  SUBMENU:=GNOME desktop
  TITLE:=adwaita-icon-theme
  URL:=https://gitlab.gnome.org/GNOME/adwaita-icon-theme
  DEPENDS:=+hicolor-icon-theme
endef

MESON_ARGS += --prefix=/usr --datadir=share

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/share/pkgconfig
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/pkgconfig/adwaita-icon-theme.pc $(1)/usr/share/pkgconfig/
endef

define Package/adwaita-icons/install
	$(INSTALL_DIR) $(1)/usr/share/icons
	$(CP) $(PKG_INSTALL_DIR)/usr/share/icons/Adwaita $(1)/usr/share/icons/
endef

define Package/adwaita-icons/postinst
#!/bin/sh
if [ -z "$$IPKG_INSTROOT" ] && command -v gtk4-update-icon-cache >/dev/null 2>&1; then
	gtk4-update-icon-cache -qtf /usr/share/icons/Adwaita >/dev/null 2>&1 || true
fi
exit 0
endef

$(eval $(call BuildPackage,adwaita-icons))
