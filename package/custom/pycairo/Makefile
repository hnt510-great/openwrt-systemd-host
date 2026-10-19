include $(TOPDIR)/rules.mk
PKG_NAME:=pycairo
PKG_VERSION:=1.29.2
PKG_RELEASE:=1
PKG_SOURCE:=pycairo-1.29.2.tar.gz
PKG_SOURCE_URL:=https://files.pythonhosted.org/packages/source/p/pycairo/
PKG_HASH:=3e69fff74fe64f5ba2dfa31f67c6bdf26413342574047437d2ac520d35e9a489
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
