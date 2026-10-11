include $(TOPDIR)/rules.mk
PKG_NAME:=pycairo
PKG_VERSION:=1.29.0
PKG_RELEASE:=1
PKG_SOURCE:=pycairo-1.29.0.tar.gz
PKG_SOURCE_URL:=https://files.pythonhosted.org/packages/source/p/pycairo/
PKG_HASH:=f3f7fde97325cae80224c09f12564ef58d0d0f655da0e3b040f5807bd5bd3142
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
MESON_ARGS += -Dpython=$(HOST_PYTHON3_BIN) -Dpython.platlibdir=$(PYTHON3_PKG_DIR) -Dpython.purelibdir=$(PYTHON3_PKG_DIR) -Dtests=false
define Package/python3-cairo
  SECTION:=lang
  CATEGORY:=Languages
  SUBMENU:=Python
  TITLE:=pycairo Python bindings
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +python3-light +libcairo
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/$(PYTHON3_PKG_DIR) $(1)/usr/lib/pkgconfig $(1)/usr/include/pycairo
	$(CP) $(PKG_INSTALL_DIR)/usr/include/pycairo/. $(1)/usr/include/pycairo/
	$(CP) $(PKG_INSTALL_DIR)/$(PYTHON3_PKG_DIR)/. $(1)/$(PYTHON3_PKG_DIR)/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/pkgconfig ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/. $(1)/usr/lib/pkgconfig/
endef

define Package/python3-cairo/install
	$(INSTALL_DIR) $(1)/$(PYTHON3_PKG_DIR)
	$(CP) $(PKG_INSTALL_DIR)/$(PYTHON3_PKG_DIR)/. $(1)/$(PYTHON3_PKG_DIR)/
endef
$(eval $(call BuildPackage,python3-cairo))
