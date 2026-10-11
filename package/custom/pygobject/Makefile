include $(TOPDIR)/rules.mk
PKG_NAME:=pygobject
PKG_VERSION:=3.58.1
PKG_RELEASE:=1
PKG_SOURCE:=pygobject-3.58.1.tar.gz
PKG_SOURCE_URL:=https://download.gnome.org/sources/pygobject/3.58/
PKG_HASH:=4c80598ade17fbaa7798e01a25d0bf29ce109740786026a074c5c62bb3e79d23
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=python3/host
include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/python/python3-package.mk
include $(INCLUDE_DIR)/meson.mk
MESON_USE_STAGING_PYTHON:=1
PYTHON_BIN:=$(STAGING_DIR_HOSTPKG)/bin/python3
MESON_VARS += $(PYTHON3_VARS)
MESON_ARGS += -Dpython=$(HOST_PYTHON3_BIN) -Dpython.platlibdir=$(PYTHON3_PKG_DIR) -Dpython.purelibdir=$(PYTHON3_PKG_DIR) -Dtests=false -Dpycairo=enabled
define Package/python3-gobject
  SECTION:=lang
  CATEGORY:=Languages
  SUBMENU:=Python
  TITLE:=pygobject Python bindings
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +python3-cairo +glib2-gir +libgirepository2 +libffi
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/$(PYTHON3_PKG_DIR) $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/$(PYTHON3_PKG_DIR)/. $(1)/$(PYTHON3_PKG_DIR)/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/pkgconfig ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/. $(1)/usr/lib/pkgconfig/
endef

define Package/python3-gobject/install
	$(INSTALL_DIR) $(1)/$(PYTHON3_PKG_DIR)
	$(CP) $(PKG_INSTALL_DIR)/$(PYTHON3_PKG_DIR)/. $(1)/$(PYTHON3_PKG_DIR)/
endef
$(eval $(call BuildPackage,python3-gobject))
