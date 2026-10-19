# SPDX-License-Identifier: GPL-2.0-only

include $(TOPDIR)/rules.mk

PKG_NAME:=glib2-build-tools
PKG_VERSION:=1
PKG_RELEASE:=1
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=glib2

GLIB_NATIVE_TOOLS:=gdbus-codegen glib-genmarshal glib-mkenums \
	glib-compile-resources gobject-query gresource gio gdbus
PKG_FILE_DEPENDS:= \
	$(addprefix $(STAGING_DIR)/usr/bin/,$(GLIB_NATIVE_TOOLS)) \
	$(STAGING_DIR)/usr/share/glib-2.0/codegen

include $(INCLUDE_DIR)/package.mk

define Package/glib2-build-tools
  SECTION:=devel
  CATEGORY:=Development
  TITLE:=GLib native code generation tools
  DEPENDS:=+glib2 +glib2-utils +python3-light +python3-xml +python3-codecs +coreutils-env
endef

define Build/Compile
endef

define Package/glib2-build-tools/install
	# Only target staging is used. Keeping this separate from glib2 avoids a
	# source build cycle: glib2 -> Python -> BlueZ -> glib2.
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/share/glib-2.0
	$(INSTALL_BIN) $(addprefix $(STAGING_DIR)/usr/bin/,$(GLIB_NATIVE_TOOLS)) $(1)/usr/bin/
	$(CP) $(STAGING_DIR)/usr/share/glib-2.0/codegen $(1)/usr/share/glib-2.0/
endef

$(eval $(call BuildPackage,glib2-build-tools))
