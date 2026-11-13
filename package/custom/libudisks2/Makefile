include $(TOPDIR)/rules.mk

PKG_NAME:=libudisks2
PKG_VERSION:=2.12.0
PKG_RELEASE:=1
PKG_SOURCE:=udisks-2.12.0.tar.bz2
PKG_SOURCE_URL:=https://github.com/storaged-project/udisks/releases/download/udisks-2.12.0/
PKG_HASH:=dd709167fddf07b14f8175dbb3ab0c372147f66b437cc2341a9f97d79303c71f
PKG_BUILD_DIR:=$(BUILD_DIR)/udisks-$(PKG_VERSION)
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host gobject-introspection/host gobject-introspection

include $(INCLUDE_DIR)/package.mk

define Package/libudisks2
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=libudisks2 GNOME Settings library
  DEPENDS:=+glib2-gir +polkit
endef

CONFIGURE_ARGS += --disable-daemon --disable-man --disable-gtk-doc --enable-introspection
CONFIGURE_VARS += GI_CROSS_LAUNCHER="$(TOPDIR)/scripts/gi-target-runner" \
	GI_SCANNER="$(STAGING_DIR)/usr/bin/g-ir-scanner" GI_COMPILER="$(STAGING_DIR)/usr/bin/g-ir-compiler"

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/. $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/share/gir-1.0 ] || $(CP) $(PKG_INSTALL_DIR)/usr/share/gir-1.0 $(1)/usr/share/
endef

define Package/libudisks2/install
	$(CP) $(PKG_INSTALL_DIR)/usr $(1)/
	[ ! -d $(PKG_INSTALL_DIR)/etc ] || $(CP) $(PKG_INSTALL_DIR)/etc $(1)/
	$(RM) -r $(1)/usr/include $(1)/usr/lib/pkgconfig $(1)/usr/share/gir-1.0 $(1)/usr/share/gtk-doc $(1)/usr/share/man
	find $(1) -type f \( -name '*.a' -o -name '*.la' \) -delete
endef

$(eval $(call BuildPackage,libudisks2))
