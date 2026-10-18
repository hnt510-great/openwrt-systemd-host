include $(TOPDIR)/rules.mk

PKG_NAME:=python-pyparsing
PKG_VERSION:=3.2.5
PKG_RELEASE:=1

PYPI_NAME:=pyparsing
PKG_HASH:=2df8d5b7b2802ef88e8d016a2eb9c7aeaa923529cd251ed0fe4608275d4105b6
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
