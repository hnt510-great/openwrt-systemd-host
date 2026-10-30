include $(TOPDIR)/rules.mk

PKG_NAME:=python-pyparsing
PKG_VERSION:=3.3.3
PKG_RELEASE:=1

PYPI_NAME:=pyparsing
PKG_HASH:=928ae7e20211f3b6f3915a72f06a0cfd29ab9d24279dd6346b6b1a7146397d36
PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=LICENSE

PKG_HOST_ONLY:=1
HOST_BUILD_DEPENDS:=python3/host python-flit-core/host python-installer/host

include $(TOPDIR)/feeds/packages/lang/python/pypi.mk
include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/host-build.mk
include $(TOPDIR)/feeds/packages/lang/python/python3-package.mk
include $(TOPDIR)/feeds/packages/lang/python/python3-host-build.mk

define Package/python3-pyparsing
  SECTION:=lang
  CATEGORY:=Languages
  SUBMENU:=Python
  TITLE:=Python parsing library for build tools
  URL:=https://github.com/pyparsing/pyparsing
  BUILDONLY:=1
endef

Host/Compile=$(Py3Host/Compile/Bootstrap)

$(eval $(call Py3Package,python3-pyparsing))
$(eval $(call BuildPackage,python3-pyparsing))
$(eval $(call HostBuild))
